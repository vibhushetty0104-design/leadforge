from __future__ import annotations

import io

import pytest

from leadforge_core.csv_import import (
    MAX_COLUMNS,
    CsvFormatError,
    CsvRowLimitError,
    normalize_email,
    parse_csv,
    suggest_mapping,
    validate_row,
)

MAPPING = {
    "business_name": "name",
    "website": "site",
    "country": "country",
    "city": "city",
    "category": "category",
    "email": "email",
    "phone": "phone",
    "description": "about",
    "source_url": "source",
}


def _rows(
    content: bytes, max_rows: int = 100
) -> tuple[list[str], list[tuple[int, dict[str, str]]]]:
    parsed = parse_csv(io.BytesIO(content), max_rows=max_rows)
    return parsed.headers, list(parsed.rows)


def test_parses_rows_and_trims_cells() -> None:
    headers, rows = _rows(b"Name, Site\n Acme , acme.com\nBeta,\n")
    assert headers == ["Name", "Site"]
    assert rows == [(2, {"Name": "Acme", "Site": "acme.com"}), (3, {"Name": "Beta", "Site": ""})]


@pytest.mark.parametrize("delimiter", [";", "\t", "|"])
def test_detects_common_delimiters(delimiter: str) -> None:
    content = f"name{delimiter}city\nAcme{delimiter}Leeds\n".encode()
    assert _rows(content)[0] == ["name", "city"]


def test_handles_bom_quoted_newlines_and_commas() -> None:
    content = '﻿name,notes\n"Acme, Inc","line one\nline two"\n'.encode()
    headers, rows = _rows(content)
    assert headers == ["name", "notes"]
    assert rows[0][1]["name"] == "Acme, Inc"
    assert rows[0][1]["notes"] == "line one\nline two"


def test_windows_1252_files_are_decoded() -> None:
    _, rows = _rows("name\nCafé Münster\n".encode("cp1252"))
    assert rows[0][1]["name"] == "Café Münster"


def test_blank_lines_are_skipped_but_row_numbers_stay_accurate() -> None:
    _, rows = _rows(b"name\nAcme\n\n,\nBeta\n")
    assert [number for number, _ in rows] == [2, 5]


def test_duplicate_and_empty_headers_are_made_unique() -> None:
    assert _rows(b"name,name,\nA,B,C\n")[0] == ["name", "name (2)", "Column 3"]


def test_short_and_long_rows_are_tolerated_and_flagged() -> None:
    _, rows = _rows(b"name,city\nAcme\nBeta,Leeds,extra\n")
    assert rows[0][1] == {"name": "Acme"}
    assert rows[1][1]["__extra_columns__"] == "1"


def test_row_limit_is_enforced_while_reading() -> None:
    parsed = parse_csv(io.BytesIO(b"name\n" + b"Acme\n" * 10), max_rows=3)
    consumed = []

    def drain() -> None:
        for row in parsed.rows:
            consumed.append(row)

    with pytest.raises(CsvRowLimitError, match="at most 3"):
        drain()
    assert len(consumed) == 3


def test_rows_are_read_lazily() -> None:
    stream = io.BytesIO(b"name\n" + b"Acme\n" * 50_000)
    parsed = parse_csv(stream, max_rows=100_000)
    assert next(parsed.rows)[0] == 2
    assert stream.tell() < len(stream.getvalue())


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"", "empty"),
        (b"   \n\n", "empty"),
        (b"\x89PNG\r\n\x00\x00\x00", "binary"),
        (b",,,\nA,B,C,D\n", "column names"),
        (",".join(f"c{i}" for i in range(MAX_COLUMNS + 1)).encode() + b"\n", "at most"),
    ],
)
def test_rejects_unusable_files(content: bytes, message: str) -> None:
    with pytest.raises(CsvFormatError, match=message):
        parse_csv(io.BytesIO(content), max_rows=10)


def test_malformed_quoting_reports_the_line() -> None:
    parsed = parse_csv(io.BytesIO(b'name,city\nAcme,Leeds\n"Beta,Bradford\n'), max_rows=10)
    with pytest.raises(CsvFormatError, match="malformed"):
        list(parsed.rows)


def test_oversized_field_is_rejected_not_buffered() -> None:
    parsed = parse_csv(io.BytesIO(b"name\n" + b"x" * 70_000 + b"\n"), max_rows=10)
    with pytest.raises(CsvFormatError, match="malformed"):
        list(parsed.rows)


def test_suggest_mapping_handles_flexible_names() -> None:
    mapping = suggest_mapping(
        ["Company Name", "Website URL", "E-mail", "Tel", "Industry", "Town", "Nation", "Notes"]
    )
    assert mapping == {
        "business_name": "Company Name",
        "website": "Website URL",
        "email": "E-mail",
        "phone": "Tel",
        "category": "Industry",
        "city": "Town",
        "country": "Nation",
    }


def test_suggest_mapping_uses_each_column_once() -> None:
    assert list(suggest_mapping(["Name"]).values()) == ["Name"]


def test_validate_valid_row_normalizes_everything() -> None:
    result = validate_row(
        {
            "name": "Acme Ltd",
            "site": "WWW.Acme.com/",
            "country": "United Kingdom",
            "city": "Leeds",
            "category": "Dental",
            "email": "Hello@Acme.com",
            "phone": "+44 113 000 0000",
            "about": "Clinic",
            "source": "https://directory.example.com/acme",
        },
        MAPPING,
    )
    assert result.is_valid
    assert result.warnings == []
    assert result.values["website_url"] == "https://www.acme.com/"
    assert result.values["website_url_original"] == "WWW.Acme.com/"
    assert result.values["domain"] == "acme.com"
    assert result.values["name_key"] == "acme"
    assert result.values["country_code"] == "GB"
    assert result.values["email"] == "hello@acme.com"
    assert result.values["industry"] == "Dental"


def test_only_name_is_required() -> None:
    result = validate_row({"name": "Acme"}, {"business_name": "name"})
    assert result.is_valid
    assert result.values["website_url"] is None
    assert result.values["email"] is None


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ({"name": ""}, "Business name is required"),
        ({"name": "x" * 201}, "200 characters"),
        ({"name": "A", "site": "ftp://acme.com"}, "Website"),
        ({"name": "A", "site": "http://localhost"}, "Website"),
        ({"name": "A", "site": "http://169.254.169.254/"}, "Website"),
        ({"name": "A", "email": "not-an-email"}, "Email"),
    ],
)
def test_rejected_rows_explain_why(raw: dict[str, str], message: str) -> None:
    result = validate_row(raw, MAPPING)
    assert not result.is_valid
    assert any(message in error for error in result.errors)


@pytest.mark.parametrize(
    ("raw", "field", "message"),
    [
        ({"name": "A", "country": "Narnia"}, "country_code", "not recognised"),
        ({"name": "A", "phone": "call me"}, "phone", "not a valid number"),
        ({"name": "A", "source": "http://10.0.0.1/"}, "source_url", "Source URL"),
    ],
)
def test_optional_problems_warn_and_keep_the_row(
    raw: dict[str, str], field: str, message: str
) -> None:
    result = validate_row(raw, MAPPING)
    assert result.is_valid
    assert result.values[field] is None
    assert any(message in warning for warning in result.warnings)


def test_extra_columns_produce_a_warning() -> None:
    result = validate_row({"name": "A", "__extra_columns__": "2"}, MAPPING)
    assert any("more columns" in warning for warning in result.warnings)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Sales@Example.COM", "sales@example.com"),
        ("mailto:a.b+c@sub.example.co.uk", "a.b+c@sub.example.co.uk"),
        ("no-at-sign", None),
        ("a@b", None),
        ("a b@example.com", None),
        ("@example.com", None),
    ],
)
def test_normalize_email(value: str, expected: str | None) -> None:
    assert normalize_email(value) == expected
