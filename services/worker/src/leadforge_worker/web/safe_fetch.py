"""SSRF-safe HTTP fetching.

Validating a URL string is not enough: a public hostname can resolve to a private
address, or change between the check and the connection (DNS rebinding). So the check
lives in the network layer. ``PinnedBackend`` resolves the hostname itself, requires
every answer to be public, and connects directly to a vetted IP. TLS still verifies
against the hostname, and no second lookup ever happens.

Everything else follows from treating each response as untrusted: redirects are
followed by hand and each hop is revalidated, bodies are streamed with a byte limit,
and a wall-clock deadline covers the entire fetch.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpcore
import httpx

from leadforge_core.models.base import utcnow
from leadforge_core.url_safety import (
    HostResolutionError,
    UnsafeURLError,
    normalize_public_url,
    resolve_public_addresses,
)

logger = logging.getLogger("leadforge.worker.fetch")

USER_AGENT = "LeadforgeBot/0.1 (public website metadata; no form submission)"
HTML_TYPES = ("text/html", "application/xhtml+xml")
ROBOTS_MAX_BYTES = 256 * 1024
_REDIRECTS = {301, 302, 303, 307, 308}


class FetchError(Exception):
    """A fetch that did not produce a response. ``code`` is safe to store and show."""

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class FetchLimits:
    connect_timeout: float = 5.0
    read_timeout: float = 10.0
    total_timeout: float = 25.0
    max_bytes: int = 2 * 1024 * 1024
    max_redirects: int = 5


@dataclass(frozen=True, slots=True)
class FetchResult:
    requested_url: str
    final_url: str
    status_code: int
    content_type: str
    charset: str | None
    body: bytes
    redirect_count: int
    fetched_at: datetime


Resolver = Callable[[str, int], list[str]]


class PinnedBackend(httpcore.NetworkBackend):
    """Connects only to addresses that passed the public-IP check."""

    def __init__(
        self,
        resolver: Resolver = resolve_public_addresses,
        inner: httpcore.NetworkBackend | None = None,
    ) -> None:
        self._resolver = resolver
        self._inner = inner or httpcore.SyncBackend()

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[Any] | None = None,
    ) -> httpcore.NetworkStream:
        addresses = self._resolver(host, port)  # raises UnsafeURLError before any connection
        failure: Exception | None = None
        for address in addresses:
            try:
                return self._inner.connect_tcp(
                    address,
                    port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as exc:
                failure = exc
        assert failure is not None  # the resolver never returns an empty list
        raise failure

    def connect_unix_socket(self, *args: Any, **kwargs: Any) -> httpcore.NetworkStream:
        raise UnsafeURLError("unix sockets are not allowed")


def pinned_transport() -> httpx.BaseTransport:
    transport = httpx.HTTPTransport(retries=0)
    # httpx does not expose the network backend, so rebuild its pool with ours.
    transport._pool = httpcore.ConnectionPool(
        ssl_context=httpx.create_ssl_context(),
        max_connections=4,
        max_keepalive_connections=0,
        network_backend=PinnedBackend(),
    )
    return transport


class SafeFetcher:
    def __init__(
        self,
        limits: FetchLimits | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.limits = limits or FetchLimits()
        self._client = httpx.Client(
            transport=transport or pinned_transport(),
            follow_redirects=False,
            trust_env=False,  # an inherited proxy would bypass the pinned backend
            timeout=httpx.Timeout(
                connect=self.limits.connect_timeout,
                read=self.limits.read_timeout,
                write=self.limits.read_timeout,
                pool=self.limits.connect_timeout,
            ),
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> SafeFetcher:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def fetch(
        self, url: str, *, max_bytes: int | None = None, html_only: bool = True
    ) -> FetchResult:
        """GET a page, following validated redirects. Raises FetchError on failure.

        HTTP error statuses are returned, not raised: they are facts about the site.
        """
        limit = max_bytes or self.limits.max_bytes
        deadline = time.monotonic() + self.limits.total_timeout
        current = self._validated(url)
        requested = current
        redirects = 0
        while True:
            try:
                with self._client.stream("GET", current) as response:
                    if response.status_code in _REDIRECTS and "location" in response.headers:
                        if redirects >= self.limits.max_redirects:
                            raise FetchError("too_many_redirects", "Too many redirects.")
                        redirects += 1
                        target = urljoin(current, response.headers["location"])
                        current = self._validated(target)
                        continue
                    content_type, charset = _content_type(response)
                    if html_only and response.status_code < 400 and content_type not in HTML_TYPES:
                        raise FetchError(
                            "unsupported_content",
                            f"Expected an HTML page, got {content_type or 'unknown content'}.",
                        )
                    body = _read_limited(response, limit, deadline)
                    return FetchResult(
                        requested_url=requested,
                        final_url=current,
                        status_code=response.status_code,
                        content_type=content_type,
                        charset=charset,
                        body=body,
                        redirect_count=redirects,
                        fetched_at=utcnow(),
                    )
            except HostResolutionError as exc:
                raise FetchError("dns_error", str(exc).capitalize() + ".", retryable=True) from exc
            except UnsafeURLError as exc:
                raise FetchError("unsafe_url", f"Refused: {exc}.") from exc
            except httpx.TimeoutException as exc:
                raise FetchError("timeout", "The site took too long.", retryable=True) from exc
            except (httpx.RequestError, httpx.InvalidURL) as exc:
                raise FetchError(
                    "connection_error", "Could not connect to the site.", retryable=True
                ) from exc

    def probe(self, url: str) -> FetchResult:
        """Check reachability cheaply, reading only the start of the response."""
        return self.fetch(url, max_bytes=16 * 1024, html_only=False)

    def allowed_by_robots(self, url: str) -> bool:
        """Honour robots.txt. Compliance is a floor: it never grants access to anything.

        A missing file allows crawling; a server error is treated as a disallow, per
        RFC 9309. Network failures fall through, because the page fetch that follows
        reports them properly.
        """
        parts = urlsplit(url)
        robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
        try:
            result = self.fetch(robots_url, max_bytes=ROBOTS_MAX_BYTES, html_only=False)
        except FetchError as exc:
            return exc.code not in {"unsafe_url", "too_many_redirects"}
        if result.status_code >= 500:
            return False
        if result.status_code >= 400:
            return True
        parser = RobotFileParser()
        parser.parse(result.body.decode("utf-8", "replace").splitlines())
        return parser.can_fetch(USER_AGENT.split("/", 1)[0], url)

    @staticmethod
    def _validated(url: str) -> str:
        try:
            return normalize_public_url(url).url
        except UnsafeURLError as exc:
            raise FetchError("unsafe_url", f"Refused: {exc}.") from exc


def _content_type(response: httpx.Response) -> tuple[str, str | None]:
    media_type, _, parameters = response.headers.get("content-type", "").partition(";")
    charset = None
    for parameter in parameters.split(";"):
        name, _, value = parameter.partition("=")
        if name.strip().lower() == "charset":
            charset = value.strip().strip('"') or None
    return media_type.strip().lower(), charset


def _read_limited(response: httpx.Response, limit: int, deadline: float) -> bytes:
    """Stop at the byte limit, wherever the bytes come from.

    ``Content-Length`` is only an early exit: servers can omit it or lie, and the
    decompressed size can far exceed it, so the count applies to decoded bytes.
    """
    declared = response.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > limit and limit > ROBOTS_MAX_BYTES:
        raise FetchError("too_large", "The page is larger than the size limit.")
    chunks: list[bytes] = []
    size = 0
    for chunk in response.iter_bytes(chunk_size=16 * 1024):
        size += len(chunk)
        if size > limit:
            if limit <= ROBOTS_MAX_BYTES:  # probes and robots.txt only need the start
                break
            raise FetchError("too_large", "The page is larger than the size limit.")
        chunks.append(chunk)
        if time.monotonic() > deadline:
            raise FetchError("timeout", "The site took too long.", retryable=True)
    return b"".join(chunks)
