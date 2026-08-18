"""Notification centre endpoints (spec sections 29 and 33)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.collab import Notification
from app.models.user import User
from app.schemas.common import Message, Page
from app.schemas.execution import MarkReadRequest, NotificationOut
from app.services import notification_service

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=Page[NotificationOut])
def list_notifications(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    unread_only: bool = False,
) -> Page[NotificationOut]:
    stmt = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        stmt = stmt.where(Notification.is_read.is_(False))

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar() or 0
    rows = (
        db.execute(
            stmt.order_by(Notification.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    return Page.build(
        [NotificationOut.model_validate(n) for n in rows], total, page, page_size
    )


@router.get("/unread-count")
def unread_count(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    return {"unread": notification_service.unread_count(db, user.id)}


@router.post("/mark-read", response_model=Message)
def mark_read(
    payload: MarkReadRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Message:
    count = notification_service.mark_read(db, user.id, payload.notification_ids)
    return Message(message=f"{count} notification(s) marked read.")


@router.post("/mark-all-read", response_model=Message)
def mark_all_read(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> Message:
    count = notification_service.mark_all_read(db, user.id)
    return Message(message=f"{count} notification(s) marked read.")
