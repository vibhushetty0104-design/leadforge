from __future__ import annotations

import uuid

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from leadforge_core import queue
from leadforge_core.countries import normalize_country
from leadforge_core.dedupe import (
    Candidate,
    DuplicateIndex,
    DuplicateMatch,
    MatchKind,
    domain_discriminator,
    names_match,
    normalize_business_name,
)
from leadforge_core.import_pipeline import decide
from leadforge_core.models import (
    Business,
    DuplicateAction,
    ImportRowOutcome,
    JobStatus,
    JobType,
    Organization,
)
from leadforge_core.models.base import utcnow


def _candidate(
    name: str = "Acme Dental",
    domain: str | None = "acme.com",
    country: str | None = "GB",
) -> Candidate:
    return Candidate(
        name=name,
        name_key=normalize_business_name(name),
        domain=domain,
        country_code=country,
        business_id=str(uuid.uuid4()),
    )


def _find(index: DuplicateIndex, name: str, domain: str | None, country: str | None = "GB"):  # type: ignore[no-untyped-def]
    return index.find(normalize_business_name(name), domain, country)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Acme Dental Ltd.", "acme dental"),
        ("ACME   DENTAL, LLC", "acme dental"),
        ("Café Münster GmbH", "cafe munster"),
        ("Smith & Sons", "smith and sons"),
        ("Company", "company"),
    ],
)
def test_name_normalization(value: str, expected: str) -> None:
    assert normalize_business_name(value) == expected


def test_names_match_tolerates_small_differences_only() -> None:
    assert names_match("acme dental", "acme dental clinic") is False
    assert names_match("riverside dental", "riverside dentel") is True
    assert names_match("acme", "zenith") is False
    assert names_match(None, "acme") is False


def test_same_domain_and_name_is_a_definite_duplicate() -> None:
    match = _find(DuplicateIndex([_candidate()]), "ACME Dental Ltd", "acme.com")
    assert match is not None
    assert match.kind is MatchKind.DEFINITE


def test_same_domain_with_a_different_name_is_only_possible() -> None:
    """Two tenants of one site are not the same business."""
    match = _find(DuplicateIndex([_candidate()]), "Zenith Physiotherapy", "acme.com")
    assert match is not None
    assert match.kind is MatchKind.POSSIBLE
    assert "different business name" in match.reason


def test_same_name_and_country_on_other_site_is_only_possible() -> None:
    match = _find(DuplicateIndex([_candidate()]), "Acme Dental", "acme-dental.co.uk")
    assert match is not None
    assert match.kind is MatchKind.POSSIBLE


def test_same_name_in_another_country_is_not_a_match() -> None:
    assert _find(DuplicateIndex([_candidate()]), "Acme Dental", None, "AU") is None


def test_same_name_without_country_is_not_evidence() -> None:
    assert _find(DuplicateIndex([_candidate(country=None)]), "Acme Dental", None, None) is None


def test_name_and_country_without_any_website_is_definite() -> None:
    index = DuplicateIndex([_candidate(domain=None)])
    match = _find(index, "Acme Dental", None)
    assert match is not None
    assert match.kind is MatchKind.DEFINITE


def test_shared_platforms_are_not_a_duplicate_signal() -> None:
    index = DuplicateIndex([_candidate(name="Bakery One", domain="facebook.com")])
    assert _find(index, "Plumber Two", "facebook.com") is None


def test_shared_platform_identity_is_per_url() -> None:
    first = domain_discriminator("facebook.com", "https://facebook.com/one")
    assert first != domain_discriminator("facebook.com", "https://facebook.com/two")
    assert first != ""
    assert domain_discriminator("acme.com", "https://acme.com/") == ""


def _match(kind: MatchKind, business_id: str | None = None) -> DuplicateMatch:
    return DuplicateMatch(kind, "reason", "Acme", "acme.com", business_id, None)


def test_decide_without_a_match_creates() -> None:
    assert decide(None, None, DuplicateAction.SKIP).outcome is ImportRowOutcome.CREATED


@pytest.mark.parametrize(
    ("policy", "outcome"),
    [
        (DuplicateAction.SKIP, ImportRowOutcome.SKIPPED_DUPLICATE),
        (DuplicateAction.UPDATE, ImportRowOutcome.UPDATED),
        (DuplicateAction.CREATE, ImportRowOutcome.CREATED),
    ],
)
def test_definite_duplicates_follow_the_policy(
    policy: DuplicateAction, outcome: ImportRowOutcome
) -> None:
    decision = decide(_match(MatchKind.DEFINITE, str(uuid.uuid4())), None, policy)
    assert decision.outcome is outcome


@pytest.mark.parametrize("policy", list(DuplicateAction))
def test_possible_duplicates_never_follow_the_policy(policy: DuplicateAction) -> None:
    decision = decide(_match(MatchKind.POSSIBLE, str(uuid.uuid4())), None, policy)
    assert decision.outcome is ImportRowOutcome.NEEDS_REVIEW


def test_row_decision_beats_policy_and_marks_separate() -> None:
    decision = decide(
        _match(MatchKind.POSSIBLE, str(uuid.uuid4())), DuplicateAction.CREATE, DuplicateAction.SKIP
    )
    assert decision.outcome is ImportRowOutcome.CREATED
    assert decision.separate is True


def test_update_without_a_target_skips() -> None:
    """A duplicate of an earlier row in the same file has nothing to update yet."""
    decision = decide(_match(MatchKind.DEFINITE), None, DuplicateAction.UPDATE)
    assert decision.outcome is ImportRowOutcome.SKIPPED_DUPLICATE


def test_discriminator_allows_deliberate_separation_only(
    session: Session, org: Organization
) -> None:
    session.add(Business(organization_id=org.id, name="One", domain="acme.com"))
    session.add(
        Business(organization_id=org.id, name="Two", domain="acme.com", domain_discriminator="x")
    )
    session.commit()
    session.add(Business(organization_id=org.id, name="Three", domain="acme.com"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_name_key_tracks_the_name(session: Session, org: Organization) -> None:
    business = Business(organization_id=org.id, name="Acme Ltd")
    assert business.name_key == "acme"
    business.name = "Zenith GmbH"
    assert business.name_key == "zenith"


@pytest.mark.parametrize(
    ("value", "expected"),
    [("gb", "GB"), ("UK", "GB"), ("U.S.A.", "US"), ("Germany", "DE"), ("Atlantis", None)],
)
def test_normalize_country(value: str, expected: str | None) -> None:
    assert normalize_country(value) == expected


def test_enqueue_unique_prevents_active_duplicates(session: Session, org: Organization) -> None:
    first, created = queue.enqueue_unique(
        session, organization_id=org.id, job_type=JobType.WEBSITE_INSPECTION, dedupe_key="k"
    )
    assert created is True
    second, created = queue.enqueue_unique(
        session, organization_id=org.id, job_type=JobType.WEBSITE_INSPECTION, dedupe_key="k"
    )
    assert created is False
    assert second.id == first.id
    session.commit()

    queue.claim_jobs(session, worker_id="w")
    assert queue.complete_job(session, first.id, "w") is True
    session.commit()

    third, created = queue.enqueue_unique(
        session, organization_id=org.id, job_type=JobType.WEBSITE_INSPECTION, dedupe_key="k"
    )
    assert created is True
    assert third.id != first.id


def test_dedupe_keys_are_per_organization(session: Session, org: Organization) -> None:
    other = Organization(name="Other", slug="other")
    session.add(other)
    session.flush()
    for organization in (org, other):
        _, created = queue.enqueue_unique(
            session,
            organization_id=organization.id,
            job_type=JobType.IMPORT,
            dedupe_key="same",
        )
        assert created is True


def test_progress_is_fenced_to_the_lease_holder(session: Session, org: Organization) -> None:
    job = queue.enqueue(session, organization_id=org.id, job_type=JobType.IMPORT)
    session.commit()
    queue.claim_jobs(session, worker_id="w")
    session.commit()

    assert queue.update_progress(session, job.id, "other", 1, 2) is False
    assert queue.update_progress(session, job.id, "w", 5, 10) is True
    session.commit()
    session.refresh(job)
    assert (job.progress_current, job.progress_total) == (5, 10)


def test_defer_requeues_without_spending_an_attempt(session: Session, org: Organization) -> None:
    from datetime import timedelta

    job = queue.enqueue(session, organization_id=org.id, job_type=JobType.IMPORT)
    session.commit()
    queue.claim_jobs(session, worker_id="w")
    session.commit()

    assert queue.defer_job(session, job.id, "w", timedelta(minutes=5), "throttled") is True
    session.commit()
    session.refresh(job)
    assert job.status == JobStatus.QUEUED
    assert job.attempts == 0
    assert job.locked_by is None
    assert job.run_after > utcnow() + timedelta(minutes=4)
