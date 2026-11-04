from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from leadforge_core.models import AuditLog


def record(
    db: Session,
    *,
    organization_id: uuid.UUID | None,
    actor_id: uuid.UUID | None,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | None,
    request_id: str | None,
    details: dict[str, Any] | None = None,
) -> None:
    """Append an audit entry in the caller's transaction (committed with the change)."""
    db.add(
        AuditLog(
            organization_id=organization_id,
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details,
            request_id=request_id,
        )
    )
