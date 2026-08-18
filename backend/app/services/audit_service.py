"""Audit trail and status history.

Two related but differently-shaped records:

* `audit_logs`  -- who changed what, browsed as a log, holds only the fields
                   that actually changed.
* `status_history` -- one row per workflow transition, queried as a time series
                   for cycle time and bottleneck analysis.

Nothing here raises: an audit failure must never be the reason a legitimate
business operation fails, so the caller's transaction is left intact.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.enums import AuditAction
from app.models.system import AuditLog, StatusHistory
from app.models.user import User

logger = logging.getLogger(__name__)

#: Never written to the audit log even if a caller passes them.
_REDACTED_FIELDS = {"hashed_password", "password", "token", "secret"}


def _serialise(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [_serialise(v) for v in value]
    if isinstance(value, dict):
        return {k: _serialise(v) for k, v in value.items()}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def diff_fields(
    before: dict[str, Any], after: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Reduce two snapshots to only the keys whose value actually moved."""
    old: dict[str, Any] = {}
    new: dict[str, Any] = {}
    for key in set(before) | set(after):
        if key in _REDACTED_FIELDS:
            continue
        b, a = _serialise(before.get(key)), _serialise(after.get(key))
        if b != a:
            old[key] = b
            new[key] = a
    return old, new


def record(
    db: Session,
    *,
    entity_type: str,
    entity_id: uuid.UUID | None,
    action: AuditAction | str,
    actor: User | None = None,
    summary: str | None = None,
    entity_code: str | None = None,
    old_value: dict[str, Any] | None = None,
    new_value: dict[str, Any] | None = None,
    context: dict[str, str | None] | None = None,
) -> AuditLog | None:
    try:
        entry = AuditLog(
            entity_type=entity_type,
            entity_id=entity_id,
            entity_code=entity_code,
            action=str(action),
            summary=summary,
            old_value=_serialise(old_value) if old_value else None,
            new_value=_serialise(new_value) if new_value else None,
            actor_id=actor.id if actor else None,
            actor_email=actor.email if actor else None,
            ip_address=(context or {}).get("ip_address"),
            user_agent=(context or {}).get("user_agent"),
        )
        db.add(entry)
        db.flush()
        return entry
    except Exception:
        logger.exception("Failed to write audit log for %s", entity_type)
        return None


def record_change(
    db: Session,
    *,
    entity_type: str,
    entity_id: uuid.UUID,
    before: dict[str, Any],
    after: dict[str, Any],
    actor: User | None = None,
    entity_code: str | None = None,
    summary: str | None = None,
    context: dict[str, str | None] | None = None,
) -> AuditLog | None:
    """Log an update, skipping the write entirely when nothing changed."""
    old, new = diff_fields(before, after)
    if not old and not new:
        return None
    return record(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        action=AuditAction.UPDATE,
        actor=actor,
        entity_code=entity_code,
        summary=summary or f"Updated {', '.join(sorted(new))}",
        old_value=old,
        new_value=new,
        context=context,
    )


def record_status(
    db: Session,
    *,
    entity_type: str,
    entity_id: uuid.UUID,
    from_status: str | None,
    to_status: str,
    actor: User | None = None,
    note: str | None = None,
    entity_code: str | None = None,
    context: dict[str, str | None] | None = None,
) -> StatusHistory | None:
    """Append a status transition and mirror it into the audit log.

    The duration the entity spent in the previous status is computed here, at
    write time, so bottleneck reporting is a plain aggregate later.
    """
    if from_status == to_status:
        return None

    now = datetime.now(UTC)
    try:
        previous = db.execute(
            select(StatusHistory)
            .where(
                StatusHistory.entity_type == entity_type,
                StatusHistory.entity_id == entity_id,
            )
            .order_by(desc(StatusHistory.changed_at))
            .limit(1)
        ).scalar_one_or_none()

        duration = None
        if previous is not None and previous.changed_at is not None:
            prior = previous.changed_at
            if prior.tzinfo is None:
                prior = prior.replace(tzinfo=UTC)
            duration = round((now - prior).total_seconds() / 3600.0, 2)

        entry = StatusHistory(
            entity_type=entity_type,
            entity_id=entity_id,
            from_status=from_status,
            to_status=to_status,
            duration_hours=duration,
            changed_by_id=actor.id if actor else None,
            changed_at=now,
            note=note,
        )
        db.add(entry)
        db.flush()
    except Exception:
        logger.exception("Failed to write status history for %s", entity_type)
        entry = None

    record(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_code=entity_code,
        action=AuditAction.STATUS_CHANGE,
        actor=actor,
        summary=f"{from_status or 'new'} -> {to_status}",
        old_value={"status": from_status},
        new_value={"status": to_status},
        context=context,
    )
    return entry
