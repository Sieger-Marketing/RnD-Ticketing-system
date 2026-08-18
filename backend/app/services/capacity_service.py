"""Resource capacity and workload (spec sections 12 and 13).

    Working hours - Leave - Holidays = Available hours
    Allocated / Available x 100       = Utilisation

Allocation is spread across each task's planned window rather than dumped on
its due date. A 40-hour task planned across two weeks contributes 4 hours a
day, which is what makes the capacity heatmap show a realistic daily load
instead of ten idle days followed by one impossible one.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.enums import OPEN_TASK_STATUSES, TaskStatus
from app.models.execution import TimeEntry
from app.models.task import Task
from app.models.user import Holiday, LeaveRecord, User, UserCapacity
from app.services import kpi, settings_service


def _daterange(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def available_hours_by_day(
    db: Session, user: User, start: date, end: date
) -> dict[date, float]:
    """Per-day available hours for one user over a window.

    Precedence, highest first: an explicit UserCapacity override, then a
    holiday or approved leave, then the user's standard working pattern.
    """
    if end < start:
        return {}

    work_days = settings_service.working_days(db)
    baseline = float(user.standard_daily_hours or 8)

    holidays = {
        row.holiday_date
        for row in db.execute(
            select(Holiday).where(
                Holiday.holiday_date.between(start, end),
                or_(Holiday.region == "ALL", Holiday.region == (user.department or "ALL")),
            )
        ).scalars()
    }

    leave_hours: dict[date, float] = defaultdict(float)
    leave_rows = db.execute(
        select(LeaveRecord).where(
            LeaveRecord.user_id == user.id,
            LeaveRecord.status == "Approved",
            LeaveRecord.start_date <= end,
            LeaveRecord.end_date >= start,
        )
    ).scalars()
    for leave in leave_rows:
        for day in _daterange(max(leave.start_date, start), min(leave.end_date, end)):
            leave_hours[day] += float(leave.hours_per_day or baseline)

    overrides = {
        row.capacity_date: float(row.available_hours)
        for row in db.execute(
            select(UserCapacity).where(
                UserCapacity.user_id == user.id,
                UserCapacity.capacity_date.between(start, end),
            )
        ).scalars()
    }

    result: dict[date, float] = {}
    for day in _daterange(start, end):
        if day in overrides:
            result[day] = max(overrides[day], 0.0)
            continue
        if day.weekday() not in work_days or day in holidays:
            result[day] = 0.0
            continue
        result[day] = max(baseline - leave_hours.get(day, 0.0), 0.0)
    return result


def allocated_hours_by_day(
    db: Session, user_id: uuid.UUID, start: date, end: date
) -> dict[date, float]:
    """Planned load per day from the user's open tasks.

    Remaining effort is spread evenly across the working days still left in
    each task's planned window. Tasks already complete or cancelled carry no
    forward load.
    """
    if end < start:
        return {}

    work_days = settings_service.working_days(db)
    tasks = db.execute(
        select(Task).where(
            Task.assigned_to_id == user_id,
            Task.status.in_([s.value for s in OPEN_TASK_STATUSES]),
        )
    ).scalars().all()

    load: dict[date, float] = {day: 0.0 for day in _daterange(start, end)}

    for task in tasks:
        estimated = float(task.estimated_hours or 0)
        done_fraction = float(task.completion_percent or 0) / 100.0
        remaining = max(estimated * (1 - done_fraction), 0.0)
        if remaining <= 0:
            continue

        # An unscheduled task still consumes capacity; treat it as landing on
        # the window start rather than silently vanishing from the heatmap.
        task_start = task.planned_start or start
        task_end = task.planned_end or task_start

        # Work that should already have happened is pulled forward to today so
        # an overdue task shows as load now, not load in the past.
        effective_start = max(task_start, start)
        effective_end = max(task_end, effective_start)

        spread_days = [
            day
            for day in _daterange(effective_start, effective_end)
            if day.weekday() in work_days
        ]
        if not spread_days:
            spread_days = [max(effective_start, start)]

        per_day = remaining / len(spread_days)
        for day in spread_days:
            if start <= day <= end:
                load[day] = load.get(day, 0.0) + per_day

    return load


def user_capacity_summary(
    db: Session, user: User, start: date, end: date
) -> dict:
    """Everything the assignment screen needs about one person."""
    available = available_hours_by_day(db, user, start, end)
    allocated = allocated_hours_by_day(db, user.id, start, end)

    total_available = round(sum(available.values()), 2)
    total_allocated = round(sum(allocated.values()), 2)
    util = kpi.utilization(total_allocated, total_available)
    thresholds = settings_service.capacity_thresholds(db)

    open_task_count = (
        db.execute(
            select(func.count())
            .select_from(Task)
            .where(
                Task.assigned_to_id == user.id,
                Task.status.in_([s.value for s in OPEN_TASK_STATUSES]),
            )
        ).scalar()
        or 0
    )

    logged = (
        db.execute(
            select(func.coalesce(func.sum(TimeEntry.hours), 0)).where(
                TimeEntry.user_id == user.id,
                TimeEntry.entry_date.between(start, end),
            )
        ).scalar()
        or 0
    )

    next_deadline = db.execute(
        select(func.min(Task.planned_end)).where(
            Task.assigned_to_id == user.id,
            Task.status.in_([s.value for s in OPEN_TASK_STATUSES]),
            Task.planned_end.is_not(None),
        )
    ).scalar()

    return {
        "user_id": str(user.id),
        "code": user.code,
        "full_name": user.full_name,
        "designation": user.designation,
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "available_hours": total_available,
        "allocated_hours": total_allocated,
        "logged_hours": round(float(logged), 2),
        "utilization_percent": util,
        "utilization_band": kpi.utilization_band(util, thresholds),
        "open_tasks": open_task_count,
        "next_deadline": next_deadline.isoformat() if next_deadline else None,
        "skills": [
            {
                "skill_id": str(us.skill_id),
                "name": us.skill.name if us.skill else None,
                "level": us.level,
                "level_rank": us.level_rank,
            }
            for us in user.skills
        ],
        "daily": [
            {
                "date": day.isoformat(),
                "available": round(available.get(day, 0.0), 2),
                "allocated": round(allocated.get(day, 0.0), 2),
                "utilization_percent": kpi.utilization(
                    allocated.get(day, 0.0), available.get(day, 0.0)
                ),
            }
            for day in _daterange(start, end)
        ],
    }


def team_capacity(
    db: Session, user_ids: list[uuid.UUID], start: date, end: date
) -> list[dict]:
    """Capacity summaries for several people, heaviest load first."""
    if not user_ids:
        return []
    users = db.execute(select(User).where(User.id.in_(user_ids))).scalars().all()
    rows = [user_capacity_summary(db, u, start, end) for u in users]
    return sorted(
        rows, key=lambda r: (r["utilization_percent"] is None, -(r["utilization_percent"] or 0))
    )


def recommend_assignees(
    db: Session,
    *,
    candidates: list[User],
    start: date,
    end: date,
    required_skill_id: uuid.UUID | None = None,
) -> list[dict]:
    """Rank people for a task by skill fit, then by spare capacity.

    Skill is the primary sort because assigning work to someone who cannot do
    it is not a capacity trade-off. Among people who can do it, the one with
    the most headroom wins.
    """
    rows = []
    for user in candidates:
        summary = user_capacity_summary(db, user, start, end)

        skill_rank = 0
        if required_skill_id is not None:
            match = next(
                (us for us in user.skills if us.skill_id == required_skill_id), None
            )
            skill_rank = match.level_rank if match else 0
            summary["has_required_skill"] = match is not None
        else:
            summary["has_required_skill"] = True

        summary["skill_rank"] = skill_rank
        summary["headroom_hours"] = round(
            summary["available_hours"] - summary["allocated_hours"], 2
        )
        rows.append(summary)

    return sorted(
        rows,
        key=lambda r: (
            not r["has_required_skill"],
            -r["skill_rank"],
            -r["headroom_hours"],
        ),
    )
