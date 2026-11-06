"""CSV export of businesses, buffered to a spooled temp file so memory stays bounded."""

from __future__ import annotations

import csv
import io
import tempfile
from typing import IO, Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from leadforge_api.deps import OrgContext
from leadforge_api.schemas.businesses import BusinessExportRequest
from leadforge_api.services import audit_log
from leadforge_api.services.businesses import filter_conditions
from leadforge_core.models import Business

MAX_EXPORT_ROWS = 10_000
_COLUMNS = (
    "name",
    "website_url",
    "domain",
    "industry",
    "city",
    "region",
    "country_code",
    "email",
    "phone",
    "description",
    "source_url",
    "status",
    "website_status",
    "source",
    "created_at",
)


def _safe_cell(value: Any) -> str:
    """Neutralise spreadsheet formulas: imported text is untrusted."""
    text = "" if value is None else str(value)
    return f"'{text}" if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def export_businesses(db: Session, ctx: OrgContext, body: BusinessExportRequest) -> IO[bytes]:
    conditions = filter_conditions(ctx, body)
    if body.business_ids is not None:
        conditions.append(Business.id.in_(body.business_ids))
    query = (
        select(Business)
        .where(*conditions)
        .order_by(Business.created_at.desc(), Business.id.desc())
        .limit(MAX_EXPORT_ROWS)
        .execution_options(yield_per=500)
    )

    output = tempfile.SpooledTemporaryFile(max_size=1024 * 1024)  # noqa: SIM115 - returned open
    text = io.TextIOWrapper(output, encoding="utf-8-sig", newline="")
    writer = csv.writer(text)
    writer.writerow(_COLUMNS)
    count = 0
    for business in db.scalars(query):
        writer.writerow([_safe_cell(getattr(business, column)) for column in _COLUMNS])
        count += 1
    text.flush()
    text.detach()
    output.seek(0)

    audit_log.record(
        db,
        organization_id=ctx.organization_id,
        actor_id=ctx.user_id,
        action="business.exported",
        entity_type="business",
        entity_id=None,
        request_id=ctx.request_id,
        details={"rows": count},
    )
    db.commit()
    return output
