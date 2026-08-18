"""Capacity, workload, leave and holiday endpoints (spec sections 12 and 13)."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import (
    AccessScope,
    get_current_user,
    get_scope,
    require_any_permission,
    require_permission,
)
from app.core.errors import NotFoundError
from app.core.permissions import P
from app.db.session import get_db
from app.models.task import Task
from app.models.user import Holiday, LeaveRecord, Role, User, UserCapacity, UserRole
from app.schemas.common import Message
from app.schemas.people import (
    CapacityOverride,
    CapacitySummary,
    HolidayCreate,
    HolidayOut,
    LeaveCreate,
    LeaveOut,
)
from app.services import analytics_service, capacity_service, settings_service

router = APIRouter(prefix="/resources", tags=["resources"])

#: Default planning window when the caller does not specify one.
DEFAULT_WINDOW_DAYS = 14


def _window(start: date | None, end: date | None) -> tuple[date, date]:
    start = start or date.today()
    end = end or (start + timedelta(days=DEFAULT_WINDOW_DAYS))
    return start, end


def _candidate_users(db: Session, scope: AccessScope) -> list[User]:
    """The people whose capacity the caller may look at.

    Restricted to staff who actually execute design work. A Director or Design
    Manager holds no tasks, so listing them would show permanently-idle rows on
    the heatmap and offer them as assignment candidates.
    """
    staff = analytics_service.execution_staff(db)
    if P.RESOURCE_VIEW_ALL in scope.permissions:
        return staff
    visible = {u.id for u in scope.user.direct_reports} | {scope.user.id}
    return [u for u in staff if u.id in visible]


@router.get("/capacity", response_model=list[CapacitySummary])
def capacity(
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(
        get_scope
    ),
    _: User = Depends(
        require_any_permission(P.RESOURCE_VIEW_ALL, P.RESOURCE_VIEW_TEAM)
    ),
    start: date | None = None,
    end: date | None = None,
    user_ids: list[uuid.UUID] | None = Query(None),
) -> list[CapacitySummary]:
    """Utilisation for a set of people over a window, most loaded first."""
    start, end = _window(start, end)

    users = _candidate_users(db, scope)
    if user_ids:
        wanted = set(user_ids)
        for target in wanted:
            scope.assert_can_view_user(target)
        users = [u for u in users if u.id in wanted]

    rows = capacity_service.team_capacity(db, [u.id for u in users], start, end)
    return [CapacitySummary(**row) for row in rows]


@router.get("/capacity/me", response_model=CapacitySummary)
def my_capacity(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    start: date | None = None,
    end: date | None = None,
) -> CapacitySummary:
    start, end = _window(start, end)
    return CapacitySummary(**capacity_service.user_capacity_summary(db, user, start, end))


@router.get("/heatmap")
def heatmap(
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_scope),
    _: User = Depends(
        require_any_permission(P.RESOURCE_VIEW_ALL, P.RESOURCE_VIEW_TEAM)
    ),
    start: date | None = None,
    end: date | None = None,
) -> dict:
    """Designer x date planned workload for the capacity heatmap."""
    start, end = _window(start, end)
    users = _candidate_users(db, scope)
    rows = capacity_service.team_capacity(db, [u.id for u in users], start, end)

    days: list[str] = []
    cursor = start
    while cursor <= end:
        days.append(cursor.isoformat())
        cursor += timedelta(days=1)

    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "days": days,
        "thresholds": settings_service.capacity_thresholds(db),
        "rows": [
            {
                "user_id": row["user_id"],
                "full_name": row["full_name"],
                "utilization_percent": row["utilization_percent"],
                "utilization_band": row["utilization_band"],
                "cells": row["daily"],
            }
            for row in rows
        ],
    }


@router.get("/assignment-board", response_model=list[CapacitySummary])
def assignment_board(
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_scope),
    _: User = Depends(require_permission(P.TASK_ASSIGN)),
    task_id: uuid.UUID | None = None,
    required_skill_id: uuid.UUID | None = None,
    start: date | None = None,
    end: date | None = None,
) -> list[CapacitySummary]:
    """Who to give a task to: skill fit first, then spare capacity.

    Passing `task_id` reads the requirement and window from the task itself,
    which is what the assignment screen does (spec section 13).
    """
    if task_id is not None:
        task = db.get(Task, task_id)
        if task is None:
            raise NotFoundError("Task not found.")
        required_skill_id = required_skill_id or task.required_skill_id

        # The task's own window is the wrong denominator for "who is free".
        # A two-day task window gives everyone 16 hours of capacity, so anyone
        # carrying a normal workload reads as 300% overloaded and the bands
        # stop distinguishing anyone. Measure from today (past windows are
        # gone) out to at least the standard planning horizon, extending to the
        # task's deadline when that is further away.
        today = date.today()
        start = start or max(task.planned_start or today, today)
        horizon = start + timedelta(days=DEFAULT_WINDOW_DAYS)
        end = end or max(task.planned_end or horizon, horizon)

    start, end = _window(start, end)
    candidates = _candidate_users(db, scope)
    rows = capacity_service.recommend_assignees(
        db,
        candidates=candidates,
        start=start,
        end=end,
        required_skill_id=required_skill_id,
    )
    return [CapacitySummary(**row) for row in rows]


@router.post("/capacity/override", response_model=Message)
def set_capacity_override(
    payload: CapacityOverride,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(P.RESOURCE_MANAGE)),
) -> Message:
    existing = db.execute(
        select(UserCapacity).where(
            UserCapacity.user_id == payload.user_id,
            UserCapacity.capacity_date == payload.capacity_date,
        )
    ).scalar_one_or_none()

    if existing is None:
        db.add(UserCapacity(**payload.model_dump()))
    else:
        existing.available_hours = payload.available_hours
        existing.note = payload.note
    db.flush()
    return Message(message="Capacity override saved.")


@router.get("/leave", response_model=list[LeaveOut])
def list_leave(
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_scope),
    user_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[LeaveOut]:
    stmt = select(LeaveRecord)
    visible = scope.visible_user_ids()
    if visible is not None:
        stmt = stmt.where(LeaveRecord.user_id.in_(visible))
    if user_id:
        scope.assert_can_view_user(user_id)
        stmt = stmt.where(LeaveRecord.user_id == user_id)
    if date_from:
        stmt = stmt.where(LeaveRecord.end_date >= date_from)
    if date_to:
        stmt = stmt.where(LeaveRecord.start_date <= date_to)

    rows = db.execute(stmt.order_by(LeaveRecord.start_date.desc())).scalars().all()
    return [LeaveOut.model_validate(r) for r in rows]


@router.post("/leave", response_model=LeaveOut, status_code=201)
def create_leave(
    payload: LeaveCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(P.RESOURCE_MANAGE)),
) -> LeaveOut:
    record = LeaveRecord(**payload.model_dump())
    db.add(record)
    db.flush()
    return LeaveOut.model_validate(record)


@router.get("/holidays", response_model=list[HolidayOut])
def list_holidays(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    year: int | None = None,
) -> list[HolidayOut]:
    stmt = select(Holiday)
    if year:
        stmt = stmt.where(
            Holiday.holiday_date >= date(year, 1, 1),
            Holiday.holiday_date <= date(year, 12, 31),
        )
    rows = db.execute(stmt.order_by(Holiday.holiday_date)).scalars().all()
    return [HolidayOut.model_validate(h) for h in rows]


@router.post("/holidays", response_model=HolidayOut, status_code=201)
def create_holiday(
    payload: HolidayCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(P.RESOURCE_MANAGE)),
) -> HolidayOut:
    holiday = Holiday(**payload.model_dump())
    db.add(holiday)
    db.flush()
    return HolidayOut.model_validate(holiday)
