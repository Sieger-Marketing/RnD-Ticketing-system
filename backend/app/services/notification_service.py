"""In-app notifications, with email as an optional second channel.

The bell is the primary channel and always works. Email goes through
`app.integrations.email` so switching provider (console -> SMTP -> Resend)
never touches this module or any caller.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.enums import NotificationSeverity
from app.models.collab import Notification
from app.models.user import User
from app.services import settings_service

logger = logging.getLogger(__name__)


class Event:
    """Notification event types (spec section 29)."""

    TASK_ASSIGNED = "task.assigned"
    TASK_DUE_SOON = "task.due_soon"
    TASK_OVERDUE = "task.overdue"
    TASK_BLOCKED = "task.blocked"
    TASK_DEPENDENCY_COMPLETED = "task.dependency_completed"
    REVISION_REQUESTED = "revision.requested"
    REVIEW_COMPLETED = "review.completed"
    REVIEW_PENDING = "review.pending"
    RELEASE_ASSIGNED = "release.assigned"
    RELEASE_AT_RISK = "release.at_risk"
    RELEASE_DELAYED = "release.delayed"
    RELEASE_COMPLETED = "release.completed"
    PROJECT_DELAYED = "project.delayed"
    RESOURCE_OVERLOADED = "resource.overloaded"
    CAPACITY_SHORTAGE = "capacity.shortage"
    MAJOR_REWORK = "quality.major_rework"


def notify(
    db: Session,
    *,
    user_id: uuid.UUID | None,
    event_type: str,
    title: str,
    body: str | None = None,
    severity: str = NotificationSeverity.INFO.value,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    email: bool = False,
) -> Notification | None:
    """Queue one notification. Silent no-op when there is no recipient.

    A missing recipient is normal -- an unassigned task has nobody to tell --
    so it is not treated as an error.
    """
    if user_id is None:
        return None
    try:
        note = Notification(
            user_id=user_id,
            event_type=event_type,
            title=title,
            body=body,
            severity=severity,
            entity_type=entity_type,
            entity_id=entity_id,
            email_required=email,
        )
        db.add(note)
        db.flush()
        return note
    except Exception:
        logger.exception("Failed to queue notification %s", event_type)
        return None


def notify_many(db: Session, user_ids, **kwargs) -> int:
    """Send the same notification to several people, skipping duplicates."""
    sent = 0
    for uid in {u for u in user_ids if u is not None}:
        if notify(db, user_id=uid, **kwargs) is not None:
            sent += 1
    return sent


def notify_role(db: Session, db_role_name: str, **kwargs) -> int:
    """Notify everyone holding a role -- used for manager/director escalations."""
    from app.models.user import Role, UserRole

    rows = db.execute(
        select(User.id)
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(Role.name == db_role_name, User.is_active.is_(True))
    ).all()
    return notify_many(db, [r[0] for r in rows], **kwargs)


def unread_count(db: Session, user_id: uuid.UUID) -> int:
    return (
        db.execute(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user_id, Notification.is_read.is_(False))
        ).scalar()
        or 0
    )


def mark_read(db: Session, user_id: uuid.UUID, notification_ids: list[uuid.UUID]) -> int:
    if not notification_ids:
        return 0
    result = db.execute(
        update(Notification)
        .where(
            Notification.user_id == user_id,
            Notification.id.in_(notification_ids),
            Notification.is_read.is_(False),
        )
        .values(is_read=True, read_at=datetime.now(UTC))
    )
    return result.rowcount or 0


def mark_all_read(db: Session, user_id: uuid.UUID) -> int:
    result = db.execute(
        update(Notification)
        .where(Notification.user_id == user_id, Notification.is_read.is_(False))
        .values(is_read=True, read_at=datetime.now(UTC))
    )
    return result.rowcount or 0


def email_enabled(db: Session) -> bool:
    return bool(settings_service.get_setting(db, "notifications.email_enabled", False))
