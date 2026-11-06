from __future__ import annotations

import gzip
from collections.abc import Callable, Iterator
from typing import Any

import httpcore
import httpx
import pytest

from leadforge_core.url_safety import HostResolutionError, UnsafeURLError, resolve_public_addresses
from leadforge_worker.web.safe_fetch import (
    FetchError,
    FetchLimits,
    PinnedBackend,
    SafeFetcher,
    pinned_transport,
)

HTML = {"content-type": "text/html; charset=utf-8"}


def _fetcher(handler: Callable[[httpx.Request], httpx.Response], **limits: Any) -> SafeFetcher:
    return SafeFetcher(FetchLimits(**limits), transport=httpx.MockTransport(handler))


def _code(fetcher: SafeFetcher, url: str = "https://acme.com/") -> str:
    with pytest.raises(FetchError) as caught:
        fetcher.fetch(url)
    return caught.value.code


def test_fetches_a_page() -> None:
    result = _fetcher(lambda r: httpx.Response(200, headers=HTML, content=b"<p>hi")).fetch(
        "https://acme.com/"
    )
    assert result.status_code == 200
    assert result.body == b"<p>hi"
    assert result.charset == "utf-8"
    assert result.redirect_count == 0


def test_never_sends_cookies_or_identifying_data() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, headers=HTML)

    _fetcher(handler).fetch("https://acme.com/")
    assert "cookie" not in seen[0].headers
    assert "@" not in seen[0].headers["user-agent"]


def test_follows_relative_and_absolute_redirects() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return httpx.Response(301, headers={"location": "/home"})
        if request.url.path == "/home":
            return httpx.Response(302, headers={"location": "https://www.acme.com/final"})
        return httpx.Response(200, headers=HTML)

    result = _fetcher(handler).fetch("https://acme.com/")
    assert result.final_url == "https://www.acme.com/final"
    assert result.requested_url == "https://acme.com/"
    assert result.redirect_count == 2


@pytest.mark.parametrize(
    "location",
    [
        "http://localhost/admin",
        "http://127.0.0.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.1/",
        "http://[::1]/",
        "http://[::ffff:10.0.0.1]/",
        "http://metadata.google.internal/",
        "file:///etc/passwd",
        "ftp://acme.com/",
        "gopher://acme.com/",
        "https://acme.com:8443/",
    ],
)
def test_redirects_to_forbidden_targets_are_refused(location: str) -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(302, headers={"location": location})

    assert _code(_fetcher(handler)) == "unsafe_url"
    assert len(requested) == 1  # the forbidden target was never contacted


def test_redirect_count_is_limited() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": f"{request.url.path}a"})

    assert _code(_fetcher(handler, max_redirects=3)) == "too_many_redirects"


@pytest.mark.parametrize(
    "url", ["http://localhost/", "ftp://acme.com/", "http://10.1.2.3/", "not a url"]
)
def test_unsafe_start_urls_are_refused(url: str) -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not connect")

    assert _code(_fetcher(fail), url) == "unsafe_url"


def test_timeouts_are_reported_as_retryable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(FetchError) as caught:
        _fetcher(handler).fetch("https://acme.com/")
    assert caught.value.code == "timeout"
    assert caught.value.retryable is True


def test_connection_failures_are_reported() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    assert _code(_fetcher(handler)) == "connection_error"


def test_declared_oversized_response_is_refused_unread() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={**HTML, "content-length": "99999999"}, content=b"x")

    assert _code(_fetcher(handler, max_bytes=512 * 1024)) == "too_large"


def test_body_limit_applies_without_content_length() -> None:
    def stream() -> Iterator[bytes]:
        for _ in range(100):
            yield b"x" * 64 * 1024

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers=HTML, content=stream())

    assert _code(_fetcher(handler, max_bytes=512 * 1024)) == "too_large"


def test_body_limit_applies_after_decompression() -> None:
    bomb = gzip.compress(b"\0" * (4 * 1024 * 1024))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={**HTML, "content-encoding": "gzip"}, content=bomb)

    assert len(bomb) < 512 * 1024
    assert _code(_fetcher(handler, max_bytes=512 * 1024)) == "too_large"


def test_non_html_is_refused_without_reading_it() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "application/zip"}, content=b"PK")

    assert _code(_fetcher(handler)) == "unsupported_content"


def test_http_errors_are_returned_not_raised() -> None:
    result = _fetcher(lambda r: httpx.Response(503, headers=HTML)).fetch("https://acme.com/")
    assert result.status_code == 503


def test_probe_reads_only_the_start() -> None:
    def stream() -> Iterator[bytes]:
        yield b"x" * 32 * 1024
        raise AssertionError("read past the probe limit")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "application/pdf"}, content=stream())

    assert _fetcher(handler).probe("https://acme.com/").status_code == 200


def _robots(body: bytes | None, status: int = 200) -> SafeFetcher:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/robots.txt"
        return httpx.Response(status, content=body or b"")

    return _fetcher(handler)


@pytest.mark.parametrize(
    ("body", "status", "allowed"),
    [
        (b"User-agent: *\nDisallow: /\n", 200, False),
        (b"User-agent: LeadforgeBot\nDisallow: /\n", 200, False),
        (b"User-agent: *\nDisallow: /private\n", 200, True),
        (b"User-agent: Googlebot\nDisallow: /\n", 200, True),
        (None, 404, True),
        (None, 503, False),
    ],
)
def test_robots_txt_is_honoured(body: bytes | None, status: int, allowed: bool) -> None:
    assert _robots(body, status).allowed_by_robots("https://acme.com/") is allowed


class _FakeBackend(httpcore.NetworkBackend):
    def __init__(self, failures: int = 0) -> None:
        self.connected: list[str] = []
        self.failures = failures

    def connect_tcp(self, host: str, port: int, **_: Any) -> httpcore.NetworkStream:
        self.connected.append(host)
        if self.failures:
            self.failures -= 1
            raise httpcore.ConnectError("refused")
        return httpcore.MockStream([])


def test_connections_use_the_vetted_address_not_the_hostname() -> None:
    inner = _FakeBackend()
    backend = PinnedBackend(resolver=lambda host, port: ["93.184.215.14"], inner=inner)
    backend.connect_tcp("acme.com", 443)
    assert inner.connected == ["93.184.215.14"]


def test_other_vetted_addresses_are_tried_after_a_failure() -> None:
    inner = _FakeBackend(failures=1)
    backend = PinnedBackend(resolver=lambda h, p: ["93.184.215.14", "93.184.215.15"], inner=inner)
    backend.connect_tcp("acme.com", 443)
    assert inner.connected == ["93.184.215.14", "93.184.215.15"]


@pytest.mark.parametrize(
    "answers",
    [
        ["127.0.0.1"],
        ["10.0.0.5"],
        ["192.168.1.1"],
        ["169.254.169.254"],
        ["::1"],
        ["fe80::1"],
        ["fd00:ec2::254"],
        ["::ffff:127.0.0.1"],
        ["93.184.215.14", "10.0.0.5"],  # one bad answer poisons the whole set
    ],
)
def test_dns_rebinding_is_stopped_before_connecting(
    monkeypatch: pytest.MonkeyPatch, answers: list[str]
) -> None:
    """A public-looking hostname that resolves privately never gets a connection."""
    import socket

    def fake_getaddrinfo(host: str, port: int, **_: Any) -> list[Any]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (a, port)) for a in answers]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    inner = _FakeBackend()
    backend = PinnedBackend(resolver=resolve_public_addresses, inner=inner)
    with pytest.raises(UnsafeURLError):
        backend.connect_tcp("rebind.acme.com", 443)
    assert inner.connected == []


def test_rebinding_is_stopped_through_the_real_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import socket

    def fake_getaddrinfo(host: str, port: int, **_: Any) -> list[Any]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with SafeFetcher(FetchLimits(), transport=pinned_transport()) as fetcher:
        assert _code(fetcher, "https://totally-public.example.com/") == "unsafe_url"


def test_unresolvable_hosts_are_a_reachability_problem(monkeypatch: pytest.MonkeyPatch) -> None:
    import socket

    def fake_getaddrinfo(host: str, port: int, **_: Any) -> list[Any]:
        raise socket.gaierror("no such host")

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(HostResolutionError):
        resolve_public_addresses("missing.acme.com")
    with SafeFetcher(FetchLimits(), transport=pinned_transport()) as fetcher:
        assert _code(fetcher, "https://missing.example.com/") == "dns_error"


def test_unix_sockets_are_refused() -> None:
    with pytest.raises(UnsafeURLError):
        PinnedBackend().connect_unix_socket("/var/run/docker.sock")
