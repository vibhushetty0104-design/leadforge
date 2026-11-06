"""Duplicate detection for businesses.

A shared domain is strong evidence, not proof. The classifier therefore has two
levels: a *definite* duplicate (same domain and compatible name) follows the user's
chosen policy, while a *possible* duplicate (same domain with a clearly different
name, or same name and country on different sites) is surfaced for human review
and never merged automatically.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
import uuid
from collections import defaultdict
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from enum import StrEnum
from typing import Any

# Sites where many unrelated businesses live under one host, so the domain says
# nothing about identity. Identity falls back to the full URL and the name.
SHARED_PLATFORM_DOMAINS = frozenset(
    {
        "facebook.com",
        "instagram.com",
        "linkedin.com",
        "x.com",
        "twitter.com",
        "tiktok.com",
        "youtube.com",
        "pinterest.com",
        "yelp.com",
        "linktr.ee",
        "sites.google.com",
        "google.com",
        "maps.google.com",
        "business.site",
        "wa.me",
        "t.me",
    }
)

_LEGAL_SUFFIXES = frozenset(
    {
        "ltd",
        "limited",
        "llc",
        "llp",
        "inc",
        "incorporated",
        "corp",
        "corporation",
        "co",
        "company",
        "gmbh",
        "ag",
        "sarl",
        "srl",
        "bv",
        "pty",
        "plc",
        "pvt",
        "private",
        "oy",
        "ab",
        "as",
        "sa",
    }
)
NAME_MATCH_THRESHOLD = 0.85


def normalize_business_name(name: str) -> str:
    """Case, accent, punctuation and legal-suffix insensitive comparison key."""
    decomposed = unicodedata.normalize("NFKD", name)
    plain = "".join(ch for ch in decomposed if not unicodedata.combining(ch)).casefold()
    words = re.sub(r"[^\w]+", " ", plain.replace("&", " and ")).split()
    while len(words) > 1 and words[-1] in _LEGAL_SUFFIXES:
        words.pop()
    return " ".join(words)


def names_match(left_key: str | None, right_key: str | None) -> bool:
    if not left_key or not right_key:
        return False
    if left_key == right_key:
        return True
    return SequenceMatcher(None, left_key, right_key).ratio() >= NAME_MATCH_THRESHOLD


def is_shared_platform(domain: str | None) -> bool:
    return domain in SHARED_PLATFORM_DOMAINS


def domain_discriminator(domain: str | None, url: str | None) -> str:
    """Default discriminator: empty, or URL-specific on shared platforms."""
    if domain and url and is_shared_platform(domain):
        return hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]
    return ""


def separate_entity_discriminator() -> str:
    """For a record deliberately kept separate from others on its domain."""
    return uuid.uuid4().hex


class MatchKind(StrEnum):
    DEFINITE = "definite"
    POSSIBLE = "possible"


@dataclass(frozen=True, slots=True)
class Candidate:
    """An existing business, or an earlier row of the same file."""

    name: str
    name_key: str | None
    domain: str | None
    country_code: str | None
    business_id: str | None = None
    row_number: int | None = None


@dataclass(frozen=True, slots=True)
class DuplicateMatch:
    kind: MatchKind
    reason: str
    name: str
    domain: str | None
    business_id: str | None
    row_number: int | None

    def as_dict(self) -> dict[str, Any]:
        return {**asdict(self), "kind": self.kind.value}


class DuplicateIndex:
    """In-memory lookup over candidates, extended as rows are processed."""

    def __init__(self, candidates: list[Candidate] | None = None) -> None:
        self._by_domain: dict[str, list[Candidate]] = defaultdict(list)
        self._by_name: dict[str, list[Candidate]] = defaultdict(list)
        for candidate in candidates or []:
            self.add(candidate)

    def add(self, candidate: Candidate) -> None:
        if candidate.domain and not is_shared_platform(candidate.domain):
            self._by_domain[candidate.domain].append(candidate)
        if candidate.name_key:
            self._by_name[candidate.name_key].append(candidate)

    def find(
        self, name_key: str | None, domain: str | None, country_code: str | None
    ) -> DuplicateMatch | None:
        possible: DuplicateMatch | None = None
        if domain and not is_shared_platform(domain):
            for candidate in self._by_domain.get(domain, []):
                if names_match(name_key, candidate.name_key):
                    return _match(MatchKind.DEFINITE, "Same website and business name", candidate)
                possible = possible or _match(
                    MatchKind.POSSIBLE, "Same website but a different business name", candidate
                )
        if possible is None and name_key:
            for candidate in self._by_name.get(name_key, []):
                if not _countries_compatible(country_code, candidate.country_code):
                    continue
                if domain and candidate.domain and domain != candidate.domain:
                    return _match(
                        MatchKind.POSSIBLE,
                        "Same name and country on a different website",
                        candidate,
                    )
                if domain is None and candidate.domain is None and country_code:
                    return _match(MatchKind.DEFINITE, "Same name and country", candidate)
                return _match(MatchKind.POSSIBLE, "Same name and country", candidate)
        return possible


def _countries_compatible(left: str | None, right: str | None) -> bool:
    # A missing country is no evidence either way, so it cannot prove a match.
    return bool(left and right and left == right)


def _match(kind: MatchKind, reason: str, candidate: Candidate) -> DuplicateMatch:
    return DuplicateMatch(
        kind=kind,
        reason=reason,
        name=candidate.name,
        domain=candidate.domain,
        business_id=candidate.business_id,
        row_number=candidate.row_number,
    )
