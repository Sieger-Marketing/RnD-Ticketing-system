"""Time tracking endpoints."""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.deps import (
    AccessScope,
    get_current_user,
    get_scope,
    require_any_permission,
    require_permission,
)
from app.core.errors import NotFoundError, PermissionDeniedError
from app.core.permissions import P
from app.db.session import get_db
from app.models.execution import TimeEntry
from app.models.task import Task
from app.models.user import User
from app.schemas.common import Message, Page
from app.schemas.execution import TimeEntryCreate, TimeEntryOut, TimerStart
from app.services import kpi, time_service

router = APIRouter(prefix="/time", tags=["time"])


@router.get("/entries", response_model=Page[TimeEntryOut])
def list_entries(
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_scope),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user_id: uuid.UUID | None = None,
    task_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    release_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    rework_only: bool = False,
) -> Page[TimeEntryOut]:
    stmt = select(TimeEntry)

    visible = scope.visible_user_ids()
    if visible is not None:
        stmt = stmt.where(TimeEntry.user_id.in_(visible))
    if user_id:
        scope.assert_can_view_user(user_id)
        stmt = stmt.where(TimeEntry.user_id == user_id)
    if task_id:
        stmt = stmt.where(TimeEntry.task_id == task_id)
    if project_id:
        stmt = stmt.where(TimeEntry.project_id == project_id)
    if release_id:
        stmt = stmt.where(TimeEntry.release_id == release_id)
    if date_from:
        stmt = stmt.where(TimeEntry.entry_date >= date_from)
    if date_to:
        stmt = stmt.where(TimeEntry.entry_date <= date_to)
    if rework_only:
        stmt = stmt.where(TimeEntry.is_rework.is_(True))

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar() or 0
    rows = (
        db.execute(
            stmt.order_by(TimeEntry.entry_date.desc(), TimeEntry.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    return Page.build(
        [TimeEntryOut.from_model(e) for e in rows], total, page, page_size
    )


@router.get("/running", response_model=TimeEntryOut | None)
def running(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> TimeEntryOut | None:
    entry = time_service.running_timer(db, user.id)
    return TimeEntryOut.from_model(entry) if entry else None


@router.post("/start", response_model=TimeEntryOut, status_code=201)
def start_timer(
    payload: TimerStart,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(P.TIME_LOG_OWN)),
) -> TimeEntryOut:
    task = db.get(Task, payload.task_id)
    if task is None:
        raise NotFoundError("Task not found.")
    entry = time_service.start_timer(
        db, task=task, user=user, description=payload.description
    )
    return TimeEntryOut.from_model(entry)


@router.post("/stop", response_model=TimeEntryOut)
def stop_timer(
    entry_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(P.TIME_LOG_OWN)),
) -> TimeEntryOut:
    entry = time_service.stop_timer(db, user=user, entry_id=entry_id)
    return TimeEntryOut.from_model(entry)


@router.post("/entries", response_model=TimeEntryOut, status_code=201)
def log_time(
    payload: TimeEntryCreate,
    db: Session = Depends(get_db),
    # Either permission opens the door; which one you hold decides whose time
    # you may log, and that is checked below. Gating on time.log_own alone made
    # time.edit_any unreachable: a Design Manager holds the second and not the
    # first, so the only role granted "correct another user's time entry" was
    # refused before it got near the check that would have allowed it.
    user: User = Depends(
        require_any_permission(P.TIME_LOG_OWN, P.TIME_EDIT_ANY)
    ),
) -> TimeEntryOut:
    task = db.get(Task, payload.task_id)
    if task is None:
        raise NotFoundError("Task not found.")

    target = user
    if payload.user_id and payload.user_id != user.id:
        # Logging on someone else's behalf is a correction, and needs the
        # elevated permission rather than the everyday one.
        if P.TIME_EDIT_ANY not in user.permission_codes:
            raise PermissionDeniedError(
                "You do not have permission to log time for another user."
            )
        target = db.get(User, payload.user_id)
        if target is None:
            raise NotFoundError("The specified user does not exist.")

    entry = time_service.log_manual(
        db,
        task=task,
        user=target,
        entry_date=payload.entry_date,
        hours=payload.hours,
        description=payload.description,
        started_at=payload.started_at,
        ended_at=payload.ended_at,
        actor=user,
    )
    return TimeEntryOut.from_model(entry)


@router.delete("/entries/{entry_id}", response_model=Message)
def delete_entry(
    entry_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(
        require_any_permission(P.TIME_LOG_OWN, P.TIME_EDIT_ANY)
    ),
) -> Message:
    entry = db.get(TimeEntry, entry_id)
    if entry is None:
        raise NotFoundError("Time entry not found.")
    if entry.user_id != user.id and P.TIME_EDIT_ANY not in user.permission_codes:
        raise PermissionDeniedError("You can only delete your own time entries.")
    time_service.delete_entry(db, entry=entry)
    return Message(message="Time entry deleted.")


@router.get("/summary")
def time_summary(
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_scope),
    user_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict:
    """Logged, rework and planned hours for a person over a period."""
    target_id = user_id or scope.user.id
    scope.assert_can_view_user(target_id)

    filters = [TimeEntry.user_id == target_id, TimeEntry.is_running.is_(False)]
    if date_from:
        filters.append(TimeEntry.entry_date >= date_from)
    if date_to:
        filters.append(TimeEntry.entry_date <= date_to)

    total, rework = db.execute(
        select(
            func.coalesce(func.sum(TimeEntry.hours), 0),
            func.coalesce(
                func.sum(
                    case((TimeEntry.is_rework.is_(True), TimeEntry.hours), else_=0)
                ),
                0,
            ),
        ).where(*filters)
    ).one()

    return {
        "user_id": str(target_id),
        "date_from": date_from.isoformat() if date_from else None,
        "date_to": date_to.isoformat() if date_to else None,
        "logged_hours": round(float(total), 2),
        "rework_hours": round(float(rework), 2),
        "rework_percent": kpi.rework_percent(rework, total),
    }
