from __future__ import annotations

import socket
from typing import Any

import pytest

from leadforge_core.url_safety import (
    UnsafeURLError,
    normalize_public_url,
    resolve_public_addresses,
)


@pytest.mark.parametrize(
    ("raw", "url", "domain"),
    [
        ("example.com", "https://example.com/", "example.com"),
        (
            "  https://WWW.Example.COM/about?x=1#team ",
            "https://www.example.com/about?x=1",
            "example.com",
        ),
        ("http://shop.example.org:443/", "http://shop.example.org:443/", "shop.example.org"),
    ],
)
def test_normalizes_public_urls(raw: str, url: str, domain: str) -> None:
    result = normalize_public_url(raw)
    assert result.url == url
    assert result.domain == domain


def test_idn_hosts_are_punycoded() -> None:
    assert normalize_public_url("https://bücher.de/").host == "xn--bcher-kva.de"


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "ftp://example.com/",
        "javascript:alert(1)",
        "file:///etc/passwd",
        "http://localhost/",
        "http://app.localhost/",
        "http://127.0.0.1/",
        "http://127.1/",
        "http://2130706433/",
        "http://0x7f000001/",
        "http://10.0.0.5/",
        "http://172.16.3.4/",
        "http://192.168.1.1/",
        "http://100.64.0.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://metadata.google.internal/",
        "http://[::1]/",
        "http://[fd00:ec2::254]/",
        "http://[::ffff:127.0.0.1]/",
        "http://0.0.0.0/",
        "http://printer.local/",
        "http://intranet/",
        "http://user:pass@example.com/",
        "http://example.com:22/",
        "http://example.com:8080/",
        "http://exa mple.com/",
        "https://" + "a" * 2100 + ".com/",
    ],
)
def test_rejects_unsafe_urls(raw: str) -> None:
    with pytest.raises(UnsafeURLError):
        normalize_public_url(raw)


def test_resolution_rejects_private_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_getaddrinfo(host: str, port: int, **_: Any) -> list[Any]:
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.215.14", port)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.1.2.3", port)),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(UnsafeURLError):
        resolve_public_addresses("rebind.example.com")


def test_resolution_returns_vetted_public_addresses(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_getaddrinfo(host: str, port: int, **_: Any) -> list[Any]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.215.14", port))] * 2

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    assert resolve_public_addresses("example.com") == ["93.184.215.14"]
