"""Extract public metadata from HTML. Pure: no network, no database.

Only what a visitor can already see is collected, and only in small amounts: this
stores contact routes for a business, not a harvest of personal data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import unquote, urljoin, urlsplit

from bs4 import BeautifulSoup
from bs4.element import Tag

from leadforge_core.csv_import import normalize_email

MAX_HEADINGS = 40
MAX_CONTACT_LINKS = 10
MAX_EMAILS = 10
MAX_PHONES = 10
MAX_SOCIAL_LINKS = 12
_TITLE_LENGTH = 500
_DESCRIPTION_LENGTH = 2000
_HEADING_LENGTH = 200

_EMAIL_IN_TEXT = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
_NOT_EMAIL_SUFFIX = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".js", ".css")
_NOT_EMAIL_DOMAINS = ("example.com", "example.org", "sentry.io", "wixpress.com", "domain.com")
_CONTACT_WORDS = re.compile(
    r"\b(contact|contact[- ]us|get[- ]in[- ]touch|about|about[- ]us|impressum|kontakt|contacto)\b",
    re.IGNORECASE,
)
_SOCIAL_HOSTS = {
    "facebook.com": "facebook",
    "instagram.com": "instagram",
    "linkedin.com": "linkedin",
    "x.com": "x",
    "twitter.com": "x",
    "youtube.com": "youtube",
    "tiktok.com": "tiktok",
    "pinterest.com": "pinterest",
}
# Share buttons and login links, which say nothing about the business.
_SOCIAL_NOISE = re.compile(r"/(sharer|share|intent|login|signup|dialog|plugins)\b", re.IGNORECASE)


@dataclass(slots=True)
class PageData:
    title: str | None = None
    meta_description: str | None = None
    canonical_url: str | None = None
    language: str | None = None
    headings: list[dict[str, Any]] = field(default_factory=list)
    contact_links: list[dict[str, Any]] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    social_links: list[dict[str, Any]] = field(default_factory=list)


def _clean(text: str | None, limit: int) -> str | None:
    if not text:
        return None
    collapsed = " ".join(text.split())
    return collapsed[:limit] or None


def _attr(tag: Tag | None, name: str) -> str | None:
    value = tag.get(name) if tag is not None else None
    if isinstance(value, list):
        value = " ".join(value)
    return value or None


def _meta(soup: BeautifulSoup, attribute: str, value: str) -> str | None:
    found = soup.find("meta", attrs={attribute: value})
    return _attr(found if isinstance(found, Tag) else None, "content")


def _http_url(href: str, base_url: str) -> str | None:
    absolute = urljoin(base_url, href.strip())
    parts = urlsplit(absolute)
    return absolute if parts.scheme in {"http", "https"} and parts.netloc else None


def _host(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _add_email(emails: list[str], candidate: str) -> None:
    address = normalize_email(candidate)
    if (
        address is None
        or address in emails
        or address.endswith(_NOT_EMAIL_SUFFIX)
        or address.split("@", 1)[1] in _NOT_EMAIL_DOMAINS
        or len(emails) >= MAX_EMAILS
    ):
        return
    emails.append(address)


def _collect_links(soup: BeautifulSoup, base_url: str, page: PageData) -> None:
    site = _host(base_url)
    seen: set[str] = set()
    for link in soup.find_all("a", href=True):
        href = str(_attr(link, "href") or "").strip()
        scheme = href.split(":", 1)[0].lower()
        if scheme == "mailto":
            _add_email(page.emails, unquote(href[7:].split("?", 1)[0]))
            continue
        if scheme == "tel":
            number = unquote(href[4:]).strip()
            if number and number not in page.phones and len(page.phones) < MAX_PHONES:
                page.phones.append(number[:40])
            continue
        url = _http_url(href, base_url)
        if url is None or url in seen:
            continue
        seen.add(url)
        host = _host(url)
        network = _SOCIAL_HOSTS.get(host)
        if network is not None:
            path = urlsplit(url).path
            is_profile = path not in {"", "/"} and not _SOCIAL_NOISE.search(path)
            if is_profile and len(page.social_links) < MAX_SOCIAL_LINKS:
                page.social_links.append({"network": network, "url": url.split("?", 1)[0]})
            continue
        text = _clean(link.get_text(" "), 80)
        is_contact = _CONTACT_WORDS.search(text or "") or _CONTACT_WORDS.search(urlsplit(url).path)
        if is_contact and host == site and len(page.contact_links) < MAX_CONTACT_LINKS:
            page.contact_links.append({"text": text, "url": url})


def extract_page(html: bytes, *, base_url: str, charset: str | None = None) -> PageData:
    """Parse any HTML, however broken, into whatever metadata it holds."""
    soup = BeautifulSoup(html, "html.parser", from_encoding=charset)
    page = PageData()

    if soup.title is not None:
        page.title = _clean(soup.title.get_text(" "), _TITLE_LENGTH)
    page.meta_description = _clean(
        _meta(soup, "name", "description") or _meta(soup, "property", "og:description"),
        _DESCRIPTION_LENGTH,
    )
    canonical = soup.find("link", rel=lambda value: bool(value) and "canonical" in value)
    href = _attr(canonical if isinstance(canonical, Tag) else None, "href")
    page.canonical_url = _http_url(href, base_url) if href else None

    root = soup.find("html")
    language = _attr(root if isinstance(root, Tag) else None, "lang") or _meta(
        soup, "http-equiv", "content-language"
    )
    page.language = _clean(language, 35)

    for heading in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"], limit=MAX_HEADINGS):
        text = _clean(heading.get_text(" "), _HEADING_LENGTH)
        if text:
            page.headings.append({"level": int(heading.name[1]), "text": text})

    _collect_links(soup, base_url, page)

    for hidden in soup(["script", "style", "noscript", "template"]):
        hidden.decompose()
    for match in _EMAIL_IN_TEXT.findall(soup.get_text(" ")):
        _add_email(page.emails, match)
    return page
