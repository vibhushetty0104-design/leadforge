from __future__ import annotations

from leadforge_worker.web.extract import MAX_EMAILS, extract_page

BASE = "https://www.acme.com/"

PAGE = b"""<!doctype html>
<html lang="en-GB">
<head>
  <title>  Acme   Dental | Leeds </title>
  <meta name="description" content="Family dentist in Leeds.">
  <link rel="canonical" href="/home">
  <script>var contact = "hidden@acme.com";</script>
</head>
<body>
  <h1>Welcome</h1><h2>Services</h2><h3><span>Check</span>-ups</h3><h4></h4>
  <a href="/contact-us">Get in touch</a>
  <a href="/about">About</a>
  <a href="/pricing">Pricing</a>
  <a href="https://other.com/contact">Partner contact</a>
  <a href="mailto:Hello@Acme.com?subject=Hi">Email us</a>
  <a href="tel:+441130000000">Call</a>
  <a href="javascript:alert(1)">Bad</a>
  <a href="https://www.facebook.com/acmedental?ref=home">Facebook</a>
  <a href="https://www.instagram.com/acme/">Instagram</a>
  <a href="https://twitter.com/intent/tweet?url=x">Share</a>
  <a href="https://www.linkedin.com/">LinkedIn home</a>
  <p>Reception: reception@acme.com</p>
  <img src="logo@2x.png">
  <!-- commented@acme.com -->
</body></html>"""


def test_extracts_full_metadata() -> None:
    page = extract_page(PAGE, base_url=BASE)
    assert page.title == "Acme Dental | Leeds"
    assert page.meta_description == "Family dentist in Leeds."
    assert page.canonical_url == "https://www.acme.com/home"
    assert page.language == "en-GB"
    assert page.headings == [
        {"level": 1, "text": "Welcome"},
        {"level": 2, "text": "Services"},
        {"level": 3, "text": "Check -ups"},
    ]
    assert page.phones == ["+441130000000"]


def test_contact_links_stay_on_the_site() -> None:
    urls = [link["url"] for link in extract_page(PAGE, base_url=BASE).contact_links]
    assert urls == ["https://www.acme.com/contact-us", "https://www.acme.com/about"]


def test_emails_come_from_visible_content_only() -> None:
    emails = extract_page(PAGE, base_url=BASE).emails
    assert emails == ["hello@acme.com", "reception@acme.com"]


def test_social_links_are_profiles_not_share_buttons() -> None:
    assert extract_page(PAGE, base_url=BASE).social_links == [
        {"network": "facebook", "url": "https://www.facebook.com/acmedental"},
        {"network": "instagram", "url": "https://www.instagram.com/acme/"},
    ]


def test_missing_metadata_yields_empty_fields() -> None:
    page = extract_page(b"<html><body><p>Nothing here</p></body></html>", base_url=BASE)
    assert page.title is None
    assert page.meta_description is None
    assert page.canonical_url is None
    assert page.language is None
    assert page.headings == []
    assert page.emails == []


def test_open_graph_description_is_a_fallback() -> None:
    html = b'<meta property="og:description" content="From OG">'
    assert extract_page(html, base_url=BASE).meta_description == "From OG"


def test_malformed_html_is_parsed_as_far_as_possible() -> None:
    html = b'<html lang=fr><title>Broken<h1>Head<p><a href="mailto:a@acme.com">x<div></span></b>'
    page = extract_page(html, base_url=BASE)
    assert page.language == "fr"
    assert page.title is not None


def test_binary_garbage_does_not_raise() -> None:
    page = extract_page(bytes(range(256)) * 10, base_url=BASE)
    assert page.emails == []


def test_empty_document_does_not_raise() -> None:
    assert extract_page(b"", base_url=BASE).title is None


def test_declared_charset_is_used() -> None:
    html = "<title>Café</title>".encode("latin-1")
    assert extract_page(html, base_url=BASE, charset="latin-1").title == "Café"


def test_collections_are_capped() -> None:
    links = "".join(f'<a href="mailto:p{i}@acme.com">x</a>' for i in range(50))
    assert len(extract_page(links.encode(), base_url=BASE).emails) == MAX_EMAILS


def test_placeholder_and_asset_addresses_are_ignored() -> None:
    html = b"<p>you@example.com icon@2x.png support@sentry.io real@acme.com</p>"
    assert extract_page(html, base_url=BASE).emails == ["real@acme.com"]


def test_unsafe_canonical_is_dropped() -> None:
    html = b'<link rel="canonical" href="javascript:alert(1)">'
    assert extract_page(html, base_url=BASE).canonical_url is None
