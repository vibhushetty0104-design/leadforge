"""Duplicate-aware import logic shared by the API preview and the import worker.

Both paths validate and classify rows with the same functions, so what a user
reviews in the preview is what the worker later applies. The worker re-checks every
row because records may have changed between preview and confirmation.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from leadforge_core.csv_import import ValidatedRow, validate_row
from leadforge_core.dedupe import (
    Candidate,
    DuplicateIndex,
    DuplicateMatch,
    MatchKind,
    is_shared_platform,
    separate_entity_discriminator,
)
from leadforge_core.models import (
    AuditLog,
    Business,
    DuplicateAction,
    ImportBatch,
    ImportRow,
    ImportRowOutcome,
    RecordSource,
)

_CHUNK = 500
# Blank fields an ``update`` may fill. Existing values are never replaced.
_FILLABLE = (
    "website_url",
    "website_url_original",
    "domain",
    "domain_discriminator",
    "country_code",
    "city",
    "industry",
    "email",
    "phone",
    "description",
    "source_url",
)
_NEW_RECORD_FIELDS = (
    "name",
    "website_url",
    "website_url_original",
    "domain",
    "domain_discriminator",
    "country_code",
    "city",
    "industry",
    "email",
    "phone",
    "description",
    "source_url",
)


def _chunks(values: list[str]) -> Iterable[list[str]]:
    for start in range(0, len(values), _CHUNK):
        yield values[start : start + _CHUNK]


def load_candidates(
    session: Session,
    organization_id: uuid.UUID,
    domains: Iterable[str | None],
    name_keys: Iterable[str | None],
) -> list[Candidate]:
    """Existing businesses that could match any of the given domains or names."""
    domain_list = sorted({d for d in domains if d and not is_shared_platform(d)})
    name_list = sorted({n for n in name_keys if n})
    seen: dict[uuid.UUID, Candidate] = {}
    columns = (
        Business.id,
        Business.name,
        Business.name_key,
        Business.domain,
        Business.country_code,
    )
    conditions = [
        *[Business.domain.in_(chunk) for chunk in _chunks(domain_list)],
        *[Business.name_key.in_(chunk) for chunk in _chunks(name_list)],
    ]
    for condition in conditions:
        rows = session.execute(
            select(*columns).where(Business.organization_id == organization_id, condition)
        ).all()
        for business_id, name, name_key, domain, country_code in rows:
            seen[business_id] = Candidate(
                name=name,
                name_key=name_key,
                domain=domain,
                country_code=country_code,
                business_id=str(business_id),
            )
    return list(seen.values())


def validate_rows(
    rows: Iterable[ImportRow], mapping: Mapping[str, str]
) -> list[tuple[ImportRow, ValidatedRow]]:
    return [(row, validate_row(row.raw_data, mapping)) for row in rows]


def candidate_for_row(row_number: int, values: Mapping[str, Any]) -> Candidate:
    return Candidate(
        name=values["name"],
        name_key=values["name_key"],
        domain=values["domain"],
        country_code=values["country_code"],
        row_number=row_number,
    )


def build_index(
    session: Session,
    organization_id: uuid.UUID,
    validated: Iterable[tuple[ImportRow, ValidatedRow]],
) -> DuplicateIndex:
    items = [item for _, item in validated if item.is_valid]
    return DuplicateIndex(
        load_candidates(
            session,
            organization_id,
            (item.values["domain"] for item in items),
            (item.values["name_key"] for item in items),
        )
    )


def apply_preview(row: ImportRow, item: ValidatedRow, match: DuplicateMatch | None) -> None:
    """Store validation and duplicate results on a row awaiting confirmation."""
    row.normalized = item.values
    row.errors = item.errors
    row.warnings = item.warnings
    row.duplicate = match.as_dict() if match else None
    row.has_duplicate = match is not None
    row.outcome = ImportRowOutcome.PENDING if item.is_valid else ImportRowOutcome.INVALID


def preview_batch(session: Session, batch: ImportBatch, mapping: Mapping[str, str]) -> None:
    """Validate and classify every row of a draft batch against current data."""
    rows = list(
        session.scalars(
            select(ImportRow).where(ImportRow.batch_id == batch.id).order_by(ImportRow.row_number)
        )
    )
    validated = validate_rows(rows, mapping)
    index = build_index(session, batch.organization_id, validated)
    for row, item in validated:
        if not item.is_valid:
            apply_preview(row, item, None)
            continue
        match = index.find(
            item.values["name_key"], item.values["domain"], item.values["country_code"]
        )
        apply_preview(row, item, match)
        index.add(candidate_for_row(row.row_number, item.values))
    batch.column_mapping = dict(mapping)


@dataclass(frozen=True, slots=True)
class RowDecision:
    outcome: ImportRowOutcome
    target_id: uuid.UUID | None = None
    separate: bool = False


def decide(
    match: DuplicateMatch | None,
    resolution: DuplicateAction | None,
    policy: DuplicateAction,
) -> RowDecision:
    """What to do with a valid row. An explicit row decision beats the batch policy.

    Only definite duplicates follow the policy automatically. A possible duplicate
    needs a human decision, so without one nothing is written for that row.
    """
    if match is None:
        return RowDecision(ImportRowOutcome.CREATED)
    if resolution is None:
        if match.kind is MatchKind.POSSIBLE:
            return RowDecision(ImportRowOutcome.NEEDS_REVIEW)
        resolution = policy

    target = uuid.UUID(match.business_id) if match.business_id else None
    if resolution is DuplicateAction.CREATE:
        return RowDecision(ImportRowOutcome.CREATED, separate=True)
    if resolution is DuplicateAction.UPDATE and target is not None:
        return RowDecision(ImportRowOutcome.UPDATED, target_id=target)
    return RowDecision(ImportRowOutcome.SKIPPED_DUPLICATE, target_id=target)


def create_business(
    session: Session,
    batch: ImportBatch,
    values: Mapping[str, Any],
    *,
    separate: bool,
) -> Business:
    data = {key: values[key] for key in _NEW_RECORD_FIELDS}
    if separate and data["domain"]:
        data["domain_discriminator"] = separate_entity_discriminator()
    business = Business(
        organization_id=batch.organization_id,
        created_by=batch.created_by,
        source=RecordSource.CSV_IMPORT,
        import_batch_id=batch.id,
        **data,
    )
    session.add(business)
    session.flush()
    return business


def fill_blank_fields(
    session: Session, batch: ImportBatch, business_id: uuid.UUID, values: Mapping[str, Any]
) -> list[str] | None:
    """Fill empty fields on an existing record. Returns changed fields, or None if gone."""
    business = session.scalar(
        select(Business).where(
            Business.id == business_id, Business.organization_id == batch.organization_id
        )
    )
    if business is None:
        return None
    changed: list[str] = []
    has_site = bool(business.domain)
    for key in _FILLABLE:
        site_field = key in {
            "website_url",
            "website_url_original",
            "domain",
            "domain_discriminator",
        }
        if site_field and (has_site or not values.get("website_url")):
            continue
        if not getattr(business, key) and values.get(key):
            setattr(business, key, values[key])
            changed.append(key)
    if changed:
        session.add(
            AuditLog(
                organization_id=batch.organization_id,
                actor_id=batch.created_by,
                action="business.updated_by_import",
                entity_type="business",
                entity_id=business.id,
                details={"import_id": str(batch.id), "fields": changed},
            )
        )
    session.flush()
    return changed


def mark_abandoned_rows(session: Session, batch_id: uuid.UUID) -> None:
    """Release raw row data once a draft is cancelled; the batch record remains."""
    session.execute(
        update(ImportRow)
        .where(ImportRow.batch_id == batch_id)
        .values(raw_data={}, normalized=None)
        .execution_options(synchronize_session=False)
    )


def duplicate_conditions(domain: str | None, name_key: str | None) -> list[Any]:
    conditions: list[Any] = []
    if domain and not is_shared_platform(domain):
        conditions.append(Business.domain == domain)
    if name_key:
        conditions.append(Business.name_key == name_key)
    return conditions


def find_business_duplicate(
    session: Session,
    organization_id: uuid.UUID,
    *,
    name_key: str | None,
    domain: str | None,
    country_code: str | None,
    exclude_id: uuid.UUID | None = None,
) -> DuplicateMatch | None:
    """Classify one prospective record against the organization's businesses."""
    conditions = duplicate_conditions(domain, name_key)
    if not conditions:
        return None
    query = select(Business).where(Business.organization_id == organization_id, or_(*conditions))
    if exclude_id is not None:
        query = query.where(Business.id != exclude_id)
    index = DuplicateIndex(
        [
            Candidate(
                name=b.name,
                name_key=b.name_key,
                domain=b.domain,
                country_code=b.country_code,
                business_id=str(b.id),
            )
            for b in session.scalars(query.limit(50))
        ]
    )
    return index.find(name_key, domain, country_code)
