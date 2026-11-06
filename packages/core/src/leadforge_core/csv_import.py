"""Streaming CSV parsing and row validation for business imports.

Parsing never holds the file in memory: rows are read one at a time from a binary
stream, and every limit (rows, columns, field size) is enforced while reading.
"""

from __future__ import annotations

import codecs
import csv
import io
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, BinaryIO

from leadforge_core.countries import normalize_country
from leadforge_core.dedupe import domain_discriminator, normalize_business_name
from leadforge_core.url_safety import UnsafeURLError, normalize_public_url

MAX_COLUMNS = 100
MAX_FIELD_BYTES = 64 * 1024
MAX_CELL_LENGTH = 5000
PREVIEW_ROWS = 10
_DELIMITERS = ",;\t|"
_EMAIL_RE = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$")
_PHONE_RE = re.compile(r"^[0-9+().\- ]{5,40}$")


class ImportField(StrEnum):
    BUSINESS_NAME = "business_name"
    WEBSITE = "website"
    COUNTRY = "country"
    CITY = "city"
    CATEGORY = "category"
    EMAIL = "email"
    PHONE = "phone"
    DESCRIPTION = "description"
    SOURCE_URL = "source_url"


_ALIASES: dict[ImportField, tuple[str, ...]] = {
    ImportField.BUSINESS_NAME: (
        "business_name",
        "business",
        "name",
        "company",
        "company_name",
        "organisation",
        "organization",
        "organization_name",
        "account",
        "account_name",
        "title",
    ),
    ImportField.WEBSITE: (
        "website",
        "website_url",
        "web_site",
        "web",
        "url",
        "site",
        "homepage",
        "domain",
        "company_website",
    ),
    ImportField.COUNTRY: ("country", "country_code", "nation"),
    ImportField.CITY: ("city", "town", "locality"),
    ImportField.CATEGORY: ("category", "industry", "sector", "type", "business_type", "niche"),
    ImportField.EMAIL: ("email", "e_mail", "email_address", "mail", "contact_email"),
    ImportField.PHONE: ("phone", "phone_number", "telephone", "tel", "mobile", "contact_number"),
    ImportField.DESCRIPTION: ("description", "about", "summary", "details"),
    ImportField.SOURCE_URL: ("source_url", "source", "source_link", "listing_url", "reference"),
}


class CsvFormatError(ValueError):
    """The file cannot be read as a CSV; the message is safe to show to users."""


class CsvRowLimitError(CsvFormatError):
    pass


def _header_key(header: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", header.casefold()).strip("_")


def suggest_mapping(headers: list[str]) -> dict[str, str]:
    """Map known fields to headers by name; each header is used at most once."""
    by_key: dict[str, str] = {}
    for header in headers:
        by_key.setdefault(_header_key(header), header)
    mapping: dict[str, str] = {}
    used: set[str] = set()
    for import_field, aliases in _ALIASES.items():
        for alias in aliases:
            match = by_key.get(alias)
            if match is not None and match not in used:
                mapping[import_field.value] = match
                used.add(match)
                break
    return mapping


@dataclass(slots=True)
class ParsedCsv:
    headers: list[str]
    rows: Iterator[tuple[int, dict[str, str]]]


def _detect_encoding(stream: BinaryIO) -> str:
    """Prefer UTF-8; fall back to Windows-1252 as produced by older Excel exports."""
    stream.seek(0)
    decoder = codecs.getincrementaldecoder("utf-8-sig")()
    try:
        while chunk := stream.read(64 * 1024):
            decoder.decode(chunk)
        decoder.decode(b"", final=True)
    except UnicodeDecodeError:
        return "cp1252"
    return "utf-8-sig"


def _sniff_delimiter(sample: str) -> str:
    try:
        return csv.Sniffer().sniff(sample, delimiters=_DELIMITERS).delimiter
    except csv.Error:
        first_line = sample.split("\n", 1)[0]
        return max(_DELIMITERS, key=first_line.count) if first_line else ","


def _unique_headers(raw: list[str]) -> list[str]:
    headers: list[str] = []
    seen: dict[str, int] = {}
    for position, value in enumerate(raw, start=1):
        name = value.strip() or f"Column {position}"
        seen[name] = seen.get(name, 0) + 1
        headers.append(name if seen[name] == 1 else f"{name} ({seen[name]})")
    return headers


def parse_csv(stream: BinaryIO, *, max_rows: int) -> ParsedCsv:
    """Read the header and return a lazy row iterator.

    Rows are yielded as ``(row_number, {header: value})`` where ``row_number`` is the
    line a spreadsheet would show for simple files (the header is row 1). The stream
    must stay open while iterating.
    """
    encoding = _detect_encoding(stream)
    stream.seek(0)
    if b"\x00" in stream.read(64 * 1024):
        raise CsvFormatError("This looks like a binary file, not a CSV.")
    stream.seek(0)

    # The wrapper stays attached for the iterator's lifetime and is detached there.
    errors = "strict" if encoding == "utf-8-sig" else "replace"
    text = io.TextIOWrapper(stream, encoding=encoding, newline="", errors=errors)
    sample = text.read(8 * 1024)
    if not sample.strip():
        text.detach()
        raise CsvFormatError("The file is empty.")
    text.seek(0)

    csv.field_size_limit(MAX_FIELD_BYTES)
    reader = csv.reader(text, delimiter=_sniff_delimiter(sample), strict=True)
    try:
        first = next(reader, None)
    except csv.Error as exc:
        text.detach()
        raise CsvFormatError(f"The header row is malformed: {exc}.") from exc
    if not first or not any(cell.strip() for cell in first):
        text.detach()
        raise CsvFormatError("The first row must contain column names.")
    if len(first) > MAX_COLUMNS:
        text.detach()
        raise CsvFormatError(f"Files may have at most {MAX_COLUMNS} columns.")
    headers = _unique_headers(first)

    def rows() -> Iterator[tuple[int, dict[str, str]]]:
        count = 0
        try:
            for cells in reader:
                if not any(cell.strip() for cell in cells):
                    continue
                count += 1
                if count > max_rows:
                    raise CsvRowLimitError(f"Files may have at most {max_rows:,} data rows.")
                row = {
                    header: cell.strip()[:MAX_CELL_LENGTH]
                    for header, cell in zip(headers, cells, strict=False)
                }
                if len(cells) > len(headers):
                    row["__extra_columns__"] = str(len(cells) - len(headers))
                yield reader.line_num, row
        except csv.Error as exc:
            raise CsvFormatError(f"Line {reader.line_num} is malformed: {exc}.") from exc
        finally:
            text.detach()

    return ParsedCsv(headers=headers, rows=rows())


def normalize_email(value: str) -> str | None:
    """Lower-cased address if it has a plausible format, otherwise None."""
    candidate = value.strip().removeprefix("mailto:")
    if len(candidate) > 320 or not _EMAIL_RE.match(candidate):
        return None
    return candidate.lower()


@dataclass(slots=True)
class ValidatedRow:
    values: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.errors


def validate_row(raw: Mapping[str, str], mapping: Mapping[str, str]) -> ValidatedRow:
    """Validate one row against a column mapping.

    Name, website and email problems reject the row, because importing it would
    produce a record the user believes has data it does not. Problems with other
    optional fields only drop that value and leave a warning.
    """
    result = ValidatedRow()

    def cell(import_field: ImportField) -> str:
        header = mapping.get(import_field.value)
        return (raw.get(header) or "").strip() if header else ""

    if raw.get("__extra_columns__"):
        result.warnings.append("Row has more columns than the header; extra values were ignored.")

    name = cell(ImportField.BUSINESS_NAME)
    if not name:
        result.errors.append("Business name is required.")
    elif len(name) > 200:
        result.errors.append("Business name must be 200 characters or fewer.")
    result.values["name"] = name
    result.values["name_key"] = normalize_business_name(name)[:200] or None

    website = cell(ImportField.WEBSITE)
    result.values["website_url"] = None
    result.values["website_url_original"] = None
    result.values["domain"] = None
    result.values["domain_discriminator"] = ""
    if website:
        try:
            normalized = normalize_public_url(website)
        except UnsafeURLError as exc:
            result.errors.append(f"Website: {exc}.")
        else:
            result.values["website_url"] = normalized.url
            result.values["website_url_original"] = normalized.original
            result.values["domain"] = normalized.domain
            result.values["domain_discriminator"] = domain_discriminator(
                normalized.domain, normalized.url
            )

    email = cell(ImportField.EMAIL)
    result.values["email"] = None
    if email:
        result.values["email"] = normalize_email(email)
        if result.values["email"] is None:
            result.errors.append(f"Email: {email!r} is not a valid address.")

    country = cell(ImportField.COUNTRY)
    result.values["country_code"] = normalize_country(country) if country else None
    if country and result.values["country_code"] is None:
        result.warnings.append(f"Country {country!r} was not recognised and was left blank.")

    phone = cell(ImportField.PHONE)
    result.values["phone"] = phone if _PHONE_RE.match(phone) else None
    if phone and result.values["phone"] is None:
        result.warnings.append(f"Phone {phone!r} is not a valid number and was left blank.")

    source_url = cell(ImportField.SOURCE_URL)
    result.values["source_url"] = None
    if source_url:
        try:
            result.values["source_url"] = normalize_public_url(source_url).url
        except UnsafeURLError:
            result.warnings.append("Source URL is not a public web address and was left blank.")

    city = cell(ImportField.CITY)
    category = cell(ImportField.CATEGORY)
    result.values["city"] = city[:120] or None
    result.values["industry"] = category[:120] or None
    if len(city) > 120 or len(category) > 120:
        result.warnings.append("City or category was shortened to 120 characters.")
    result.values["description"] = cell(ImportField.DESCRIPTION) or None
    return result
