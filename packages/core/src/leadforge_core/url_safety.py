"""Validation of user-supplied and crawler-visited URLs.

Two layers:

* :func:`normalize_public_url` — syntactic checks run on import / API input. It
  rejects anything that is obviously not a public website (private IP literals,
  localhost, internal TLDs, credentials in the URL, odd ports) without doing DNS.
* :func:`resolve_public_addresses` — the network-level check the crawler must run
  immediately before every connection, including after each redirect, so that a
  public name that resolves to a private address (DNS rebinding) is refused.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

MAX_URL_LENGTH = 2048
ALLOWED_SCHEMES = frozenset({"http", "https"})
ALLOWED_PORTS = frozenset({None, 80, 443})

_BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "metadata",
        "metadata.google.internal",
        "metadata.goog",
        "instance-data",
        "instance-data.ec2.internal",
    }
)
_BLOCKED_SUFFIXES = (
    ".localhost",
    ".local",
    ".internal",
    ".intranet",
    ".lan",
    ".home",
    ".home.arpa",
    ".corp",
    ".private",
    ".localdomain",
    ".test",
    ".invalid",
    ".example",
    ".onion",
)
_LABEL_RE = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")


class UnsafeURLError(ValueError):
    """The URL is malformed or points somewhere LEADFORGE must not connect to."""


@dataclass(frozen=True, slots=True)
class NormalizedURL:
    url: str
    host: str
    domain: str


def is_public_ip(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """True only for globally routable unicast addresses."""
    if isinstance(address, ipaddress.IPv6Address):
        # Unwrap IPv6 forms that embed an IPv4 address and check that address.
        embedded = address.ipv4_mapped or address.sixtofour
        if embedded is None and address.teredo is not None:
            embedded = address.teredo[1]
        if embedded is not None:
            return is_public_ip(embedded)
    return bool(
        address.is_global
        and not address.is_multicast
        and not address.is_reserved
        and not address.is_loopback
        and not address.is_link_local
        and not address.is_private
        and not address.is_unspecified
    )


def _parse_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return None


def _validate_hostname(host: str) -> None:
    if len(host) > 253:
        raise UnsafeURLError("hostname is too long")
    if host in _BLOCKED_HOSTNAMES or host.endswith(_BLOCKED_SUFFIXES):
        raise UnsafeURLError("internal or reserved hostnames are not allowed")
    labels = host.split(".")
    if len(labels) < 2:
        raise UnsafeURLError("hostname must be a fully qualified public domain")
    if not all(_LABEL_RE.match(label) for label in labels):
        raise UnsafeURLError("hostname contains invalid characters")
    # Numeric TLDs indicate shorthand IPv4 such as "127.1" or "10.0.1".
    if labels[-1].isdigit():
        raise UnsafeURLError("numeric hostnames are not allowed")


def normalize_public_url(raw: str) -> NormalizedURL:
    """Normalise a website URL and reject non-public destinations.

    Bare domains ("example.com") are accepted and upgraded to ``https://``.
    """
    candidate = raw.strip()
    if not candidate:
        raise UnsafeURLError("URL is empty")
    if len(candidate) > MAX_URL_LENGTH:
        raise UnsafeURLError("URL is too long")
    if any(ch.isspace() or ord(ch) < 0x20 for ch in candidate):
        raise UnsafeURLError("URL contains whitespace or control characters")
    if "://" not in candidate:
        candidate = "https://" + candidate

    try:
        parts = urlsplit(candidate)
        port = parts.port
    except ValueError as exc:
        raise UnsafeURLError("URL is malformed") from exc

    scheme = parts.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise UnsafeURLError("only http and https URLs are allowed")
    if parts.username is not None or parts.password is not None:
        raise UnsafeURLError("URLs containing credentials are not allowed")
    if port not in ALLOWED_PORTS:
        raise UnsafeURLError("only the default web ports (80, 443) are allowed")

    raw_host = parts.hostname
    if not raw_host:
        raise UnsafeURLError("URL has no hostname")

    ip = _parse_ip(raw_host)
    if ip is not None:
        if not is_public_ip(ip):
            raise UnsafeURLError("private, loopback and reserved IP addresses are not allowed")
        host = ip.compressed if ip.version == 4 else f"[{ip.compressed}]"
    else:
        try:
            host = raw_host.rstrip(".").encode("idna").decode("ascii").lower()
        except UnicodeError as exc:
            raise UnsafeURLError("hostname is not a valid domain name") from exc
        _validate_hostname(host)

    netloc = host if port is None else f"{host}:{port}"
    path = parts.path or "/"
    url = urlunsplit((scheme, netloc, path, parts.query, ""))
    if len(url) > MAX_URL_LENGTH:
        raise UnsafeURLError("URL is too long")

    domain = host[4:] if host.startswith("www.") else host
    return NormalizedURL(url=url, host=host, domain=domain)


def resolve_public_addresses(host: str, port: int = 443) -> list[str]:
    """Resolve ``host`` and require that *every* returned address is public.

    Returns the vetted addresses so the caller can pin the connection to them
    rather than resolving a second time (which would reopen a rebinding window).
    """
    literal = _parse_ip(host)
    if literal is not None:
        if not is_public_ip(literal):
            raise UnsafeURLError("address is not publicly routable")
        return [literal.compressed]

    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeURLError(f"could not resolve {host}") from exc

    addresses: list[str] = []
    for info in infos:
        address = ipaddress.ip_address(str(info[4][0]).split("%", 1)[0])
        if not is_public_ip(address):
            raise UnsafeURLError(f"{host} resolves to a non-public address")
        addresses.append(address.compressed)
    if not addresses:
        raise UnsafeURLError(f"could not resolve {host}")
    return sorted(set(addresses))
