"""Dashboard and analytics aggregation (spec sections 18, 22-27 and 46).

Everything here is computed from transactional rows through app.services.kpi.
There is no metrics table, no cached snapshot and no duplicated formula: a
number on the Director's dashboard and the same number on a designer's
personal page come from the same function.

Queries are written as aggregates rather than row loops, because the target is
100k+ tasks and 1M+ time entries (spec section 44).
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import Select, case, false, func, or_, select
from sqlalchemy.orm import Session

from app.core.enums import (
    OPEN_TASK_STATUSES,
    Accountability,
    HealthStatus,
    Priority,
    ProjectStatus,
    ReleaseStatus,
    ReviewResult,
    ReviewStatus,
    RevisionStatus,
    TaskStatus,
)
from app.models.execution import Review, Revision, TimeEntry
from app.models.project import Project
from app.models.release import DesignRelease
from app.models.task import Task
from app.models.user import Role, User, UserRole
from app.services import capacity_service, kpi, settings_service

_OPEN_TASKS = [s.value for s in OPEN_TASK_STATUSES]
_DONE_TASKS = [TaskStatus.COMPLETED.value, TaskStatus.APPROVED.value]
_ACTIVE_PROJECTS = [
    s.value
    for s in ProjectStatus
    if s not in {ProjectStatus.COMPLETED, ProjectStatus.CANCELLED}
]
_ACTIVE_RELEASES = [
    s.value
    for s in ReleaseStatus
    if s not in {ReleaseStatus.COMPLETED, ReleaseStatus.CANCELLED}
]


def _scalar(db: Session, stmt: Select) -> float:
    return float(db.execute(stmt).scalar() or 0)


def _count(db: Session, model, *filters) -> int:
    return int(
        db.execute(select(func.count()).select_from(model).where(*filters)).scalar() or 0
    )


# ---------------------------------------------------------------------------
# On-time completion
# ---------------------------------------------------------------------------


def _on_time_counts(db: Session, *filters) -> tuple[int, int]:
    """(completed_on_time, completed_total) for tasks matching `filters`.

    "On time" compares the completion timestamp against the planned end date.
    Tasks with no planned end are excluded from both numbers rather than
    counted as on time, which would flatter the metric.
    """
    row = db.execute(
        select(
            func.count(),
            func.coalesce(
                func.sum(
                    case(
                        (
                            func.date(Task.completed_at) <= Task.planned_end,
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
        )
        .select_from(Task)
        .where(
            Task.status.in_(_DONE_TASKS),
            Task.completed_at.is_not(None),
            Task.planned_end.is_not(None),
            *filters,
        )
    ).one()
    return int(row[1] or 0), int(row[0] or 0)


# ---------------------------------------------------------------------------
# Department
# ---------------------------------------------------------------------------


def department_metrics(
    db: Session, *, date_from: date | None = None, date_to: date | None = None
) -> dict:
    """The department-level KPI set (spec section 18)."""
    today = date.today()
    date_from = date_from or (today - timedelta(days=90))
    date_to = date_to or today

    time_filters = [
        TimeEntry.is_running.is_(False),
        TimeEntry.entry_date.between(date_from, date_to),
    ]
    actual_hours, rework_hours = db.execute(
        select(
            func.coalesce(func.sum(TimeEntry.hours), 0),
            func.coalesce(
                func.sum(case((TimeEntry.is_rework.is_(True), TimeEntry.hours), else_=0)),
                0,
            ),
        ).where(*time_filters)
    ).one()

    planned_hours = _scalar(
        db,
        select(func.coalesce(func.sum(Task.estimated_hours), 0)).where(
            Task.status.in_(_DONE_TASKS),
            Task.completed_at.is_not(None),
            func.date(Task.completed_at).between(date_from, date_to),
        ),
    )
    completed_actual = _scalar(
        db,
        select(func.coalesce(func.sum(Task.actual_hours), 0)).where(
            Task.status.in_(_DONE_TASKS),
            Task.completed_at.is_not(None),
            func.date(Task.completed_at).between(date_from, date_to),
        ),
    )

    on_time, completed_total = _on_time_counts(
        db, func.date(Task.completed_at).between(date_from, date_to)
    )

    reviews = db.execute(select(Review)).scalars().all()
    submitted_tasks = {r.task_id for r in reviews}
    first_pass_tasks = {
        r.task_id
        for r in reviews
        if r.round_number == 1 and r.result == ReviewResult.APPROVED.value
    }

    cycle_times = [
        kpi.cycle_time_hours(t.started_at, t.completed_at)
        for t in db.execute(
            select(Task).where(
                Task.status.in_(_DONE_TASKS),
                Task.started_at.is_not(None),
                Task.completed_at.is_not(None),
                func.date(Task.completed_at).between(date_from, date_to),
            )
        ).scalars()
    ]

    # The KPI period is historical, so utilisation is measured from hours
    # actually logged rather than from forward allocation.
    utilization = department_utilization(db, date_from, date_to, basis="logged")

    return {
        "period": {"from": date_from.isoformat(), "to": date_to.isoformat()},
        "active_projects": _count(db, Project, Project.status.in_(_ACTIVE_PROJECTS)),
        "completed_projects": _count(
            db, Project, Project.status == ProjectStatus.COMPLETED.value
        ),
        "active_releases": _count(
            db, DesignRelease, DesignRelease.status.in_(_ACTIVE_RELEASES)
        ),
        "overdue_releases": _count(
            db,
            DesignRelease,
            DesignRelease.delay_days > 0,
            DesignRelease.status.in_(_ACTIVE_RELEASES),
        ),
        "active_tasks": _count(db, Task, Task.status.in_(_OPEN_TASKS)),
        "completed_tasks": completed_total,
        "overdue_tasks": _count(
            db, Task, Task.planned_end < today, Task.status.in_(_OPEN_TASKS)
        ),
        "blocked_tasks": _count(db, Task, Task.status == TaskStatus.BLOCKED.value),
        "pending_reviews": _count(
            db,
            Review,
            Review.status.in_([ReviewStatus.PENDING.value, ReviewStatus.IN_REVIEW.value]),
        ),
        "open_revisions": _count(
            db,
            Revision,
            Revision.status.in_(
                [RevisionStatus.OPEN.value, RevisionStatus.IN_PROGRESS.value]
            ),
        ),
        "planned_hours": round(planned_hours, 2),
        "actual_hours": round(float(actual_hours), 2),
        "rework_hours": round(float(rework_hours), 2),
        "efficiency_percent": kpi.efficiency(planned_hours, completed_actual),
        "utilization_percent": utilization["utilization_percent"],
        "available_hours": utilization["available_hours"],
        "allocated_hours": utilization["allocated_hours"],
        "on_time_percent": kpi.on_time_percent(on_time, completed_total),
        "rework_percent": kpi.rework_percent(rework_hours, actual_hours),
        "first_pass_approval_percent": kpi.first_pass_approval_percent(
            len(first_pass_tasks), len(submitted_tasks)
        ),
        # Both halves of the ratio are the same period. Counting every revision
        # ever raised against one period's completed tasks reported rates well
        # over 100%, and forcing the denominator to a minimum of 1 turned a
        # quiet period into a four-figure percentage instead of the dash that
        # says "nothing finished, so there is nothing to divide by".
        "revision_rate_percent": kpi.revision_rate(
            _count(
                db,
                Revision,
                func.date(Revision.created_at).between(date_from, date_to),
            ),
            completed_total,
        ),
        "average_cycle_time_hours": kpi.average(cycle_times),
        "average_review_turnaround_hours": kpi.average(
            [
                float(r.turnaround_hours)
                for r in reviews
                if r.turnaround_hours is not None
            ]
        ),
        "health_breakdown": _health_breakdown(db),
    }


def department_utilization(
    db: Session, start: date, end: date, *, basis: str = "allocated"
) -> dict:
    """Aggregate capacity across everyone who executes design work.

    The basis matters and is not interchangeable:

    * `allocated` answers "is the plan feasible?" and only makes sense for a
      forward window, because allocation is remaining effort on open tasks.
    * `logged`  answers "how busy were we?" and is the only honest basis for a
      period that has already happened -- comparing forward-looking allocation
      against a 90-day capacity denominator would report a near-zero
      utilisation for a fully occupied department.
    """
    designers = execution_staff(db)
    rows = capacity_service.team_capacity(db, [u.id for u in designers], start, end)
    available = round(sum(r["available_hours"] for r in rows), 2)
    allocated = round(sum(r["allocated_hours"] for r in rows), 2)
    logged = round(sum(r["logged_hours"] for r in rows), 2)

    used = logged if basis == "logged" else allocated
    return {
        "basis": basis,
        "available_hours": available,
        "allocated_hours": allocated,
        "logged_hours": logged,
        "utilization_percent": kpi.utilization(used, available),
        "people": len(rows),
    }


def execution_staff(db: Session) -> list[User]:
    """Everyone who actually executes design work: Designers and Team Leads.

    Directors and Design Managers are deliberately excluded. They hold no
    design tasks, so including them would dilute department utilisation with
    permanently-idle rows and would offer them as assignment candidates.
    """
    return (
        db.execute(
            select(User)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .where(User.is_active.is_(True), Role.name.in_(["Designer", "Team Lead"]))
            .distinct()
        )
        .scalars()
        .all()
    )


def team_leads(db: Session) -> list[User]:
    """Active Team Leads, for the reports and scorecards that group by them."""
    return (
        db.execute(
            select(User)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .where(User.is_active.is_(True), Role.name == "Team Lead")
            .order_by(User.full_name)
            .distinct()
        )
        .scalars()
        .all()
    )


def _health_breakdown(db: Session) -> dict:
    rows = db.execute(
        select(Project.health, func.count())
        .where(Project.status.in_(_ACTIVE_PROJECTS))
        .group_by(Project.health)
    ).all()
    counts = {h.value: 0 for h in HealthStatus}
    for health, count in rows:
        counts[health] = count
    return counts


# ---------------------------------------------------------------------------
# Individual performance
# ---------------------------------------------------------------------------


def designer_metrics(
    db: Session,
    user: User,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict:
    """Everything on a designer's scorecard (spec section 18)."""
    today = date.today()
    date_from = date_from or (today - timedelta(days=30))
    date_to = date_to or today

    assigned = _count(db, Task, Task.assigned_to_id == user.id)
    pending = _count(
        db, Task, Task.assigned_to_id == user.id, Task.status.in_(_OPEN_TASKS)
    )
    overdue = _count(
        db,
        Task,
        Task.assigned_to_id == user.id,
        Task.status.in_(_OPEN_TASKS),
        Task.planned_end < today,
    )

    completed_tasks = (
        db.execute(
            select(Task).where(
                Task.assigned_to_id == user.id,
                Task.status.in_(_DONE_TASKS),
                Task.completed_at.is_not(None),
                func.date(Task.completed_at).between(date_from, date_to),
            )
        )
        .scalars()
        .all()
    )

    planned = sum(float(t.estimated_hours or 0) for t in completed_tasks)
    actual = sum(float(t.actual_hours or 0) for t in completed_tasks)

    logged, rework = db.execute(
        select(
            func.coalesce(func.sum(TimeEntry.hours), 0),
            func.coalesce(
                func.sum(case((TimeEntry.is_rework.is_(True), TimeEntry.hours), else_=0)),
                0,
            ),
        ).where(
            TimeEntry.user_id == user.id,
            TimeEntry.is_running.is_(False),
            TimeEntry.entry_date.between(date_from, date_to),
        )
    ).one()

    on_time, completed_total = _on_time_counts(
        db,
        Task.assigned_to_id == user.id,
        func.date(Task.completed_at).between(date_from, date_to),
    )

    task_ids = [
        row[0]
        for row in db.execute(
            select(Task.id).where(Task.assigned_to_id == user.id)
        ).all()
    ]
    first_pass = _first_pass_for_tasks(db, task_ids)

    # Only controllable revisions count against the person; a customer change
    # is not a quality failure on their part (spec section 16).
    controllable_revisions = _count(
        db,
        Revision,
        Revision.assigned_to_id == user.id,
        Revision.accountability == Accountability.CONTROLLABLE.value,
    )
    total_revisions = _count(db, Revision, Revision.assigned_to_id == user.id)

    capacity = capacity_service.user_capacity_summary(db, user, date_from, date_to)
    completed_weight = sum(t.effort_weight for t in completed_tasks)

    weights = settings_service.performance_weights(db)
    score = kpi.performance_score(
        weights=weights,
        productivity_index=kpi.productivity_index(
            completed_weight, capacity["available_hours"]
        ),
        efficiency_percent=kpi.efficiency(planned, actual),
        first_pass_percent=first_pass["percent"],
        on_time_percent_value=kpi.on_time_percent(on_time, completed_total),
        utilization_percent=capacity["utilization_percent"],
        process_compliance_percent=_process_compliance(db, user),
    )

    return {
        "user": {
            "id": str(user.id),
            "code": user.code,
            "full_name": user.full_name,
            "designation": user.designation,
        },
        "period": {"from": date_from.isoformat(), "to": date_to.isoformat()},
        "tasks_assigned": assigned,
        "tasks_completed": len(completed_tasks),
        "tasks_pending": pending,
        "tasks_overdue": overdue,
        "planned_hours": round(planned, 2),
        "actual_hours": round(actual, 2),
        "logged_hours": round(float(logged), 2),
        "rework_hours": round(float(rework), 2),
        "blocked_hours": round(
            sum(float(t.blocked_hours or 0) for t in completed_tasks), 2
        ),
        "efficiency_percent": kpi.efficiency(planned, actual),
        "effort_variance": kpi.effort_variance(planned, actual),
        "utilization_percent": capacity["utilization_percent"],
        "utilization_band": capacity["utilization_band"],
        "available_hours": capacity["available_hours"],
        "allocated_hours": capacity["allocated_hours"],
        "on_time_percent": kpi.on_time_percent(on_time, completed_total),
        "rework_percent": kpi.rework_percent(rework, logged),
        "revision_count": total_revisions,
        "controllable_revision_count": controllable_revisions,
        "first_pass_approval_percent": first_pass["percent"],
        "average_cycle_time_hours": kpi.average(
            [kpi.cycle_time_hours(t.started_at, t.completed_at) for t in completed_tasks]
        ),
        "average_queue_time_hours": kpi.average(
            [kpi.queue_time_hours(t.assigned_at, t.started_at) for t in completed_tasks]
        ),
        "effort_weighted_output": round(completed_weight, 2),
        "performance_score": score,
    }


def _first_pass_for_tasks(db: Session, task_ids: list[uuid.UUID]) -> dict:
    if not task_ids:
        return {"submitted": 0, "approved_first_round": 0, "percent": None}
    reviews = (
        db.execute(select(Review).where(Review.task_id.in_(task_ids))).scalars().all()
    )
    submitted = {r.task_id for r in reviews}
    first = {
        r.task_id
        for r in reviews
        if r.round_number == 1 and r.result == ReviewResult.APPROVED.value
    }
    return {
        "submitted": len(submitted),
        "approved_first_round": len(first),
        "percent": kpi.first_pass_approval_percent(len(first), len(submitted)),
    }


def _process_compliance(db: Session, user: User) -> float | None:
    """How consistently the person follows the process.

    Measured as the share of their completed tasks that carry the evidence the
    process expects: time actually logged, and a delay reason when the task
    finished late. Both are things the workflow asks for explicitly, so this
    is compliance rather than a judgement about the work itself.
    """
    tasks = (
        db.execute(
            select(Task).where(
                Task.assigned_to_id == user.id, Task.status.in_(_DONE_TASKS)
            )
        )
        .scalars()
        .all()
    )
    if not tasks:
        return None

    compliant = 0
    for task in tasks:
        has_hours = float(task.actual_hours or 0) > 0
        finished_late = (
            task.planned_end
            and task.completed_at
            and task.completed_at.date() > task.planned_end
        )
        explained = (not finished_late) or bool(task.delay_reason)
        if has_hours and explained:
            compliant += 1
    return round(compliant / len(tasks) * 100, 2)


def team_lead_metrics(
    db: Session,
    lead: User,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict:
    """Team Lead scorecard, rolling up their releases and their people."""
    today = date.today()
    date_from = date_from or (today - timedelta(days=30))
    date_to = date_to or today

    releases = (
        db.execute(select(DesignRelease).where(DesignRelease.team_lead_id == lead.id))
        .scalars()
        .all()
    )
    completed_releases = [
        r for r in releases if r.status == ReleaseStatus.COMPLETED.value
    ]
    delayed_releases = [r for r in releases if (r.delay_days or 0) > 0]

    members = [u for u in lead.direct_reports if u.is_active]
    member_ids = [u.id for u in members] or [lead.id]

    planned = sum(float(r.estimated_hours or 0) for r in releases)
    actual = sum(float(r.actual_hours or 0) for r in releases)
    rework = sum(float(r.rework_hours or 0) for r in releases)

    on_time, completed_total = _on_time_counts(
        db,
        Task.assigned_to_id.in_(member_ids),
        func.date(Task.completed_at).between(date_from, date_to),
    )

    task_ids = [
        row[0]
        for row in db.execute(
            select(Task.id).where(Task.team_lead_id == lead.id)
        ).all()
    ]

    capacity_rows = capacity_service.team_capacity(db, member_ids, date_from, date_to)
    available = sum(r["available_hours"] for r in capacity_rows)
    allocated = sum(r["allocated_hours"] for r in capacity_rows)

    turnarounds = [
        float(r.turnaround_hours)
        for r in db.execute(
            select(Review).where(
                Review.reviewer_id == lead.id, Review.turnaround_hours.is_not(None)
            )
        ).scalars()
    ]

    return {
        "user": {
            "id": str(lead.id),
            "code": lead.code,
            "full_name": lead.full_name,
        },
        "period": {"from": date_from.isoformat(), "to": date_to.isoformat()},
        "releases_assigned": len(releases),
        "releases_completed": len(completed_releases),
        "releases_delayed": len(delayed_releases),
        "team_size": len(members),
        "planned_hours": round(planned, 2),
        "actual_hours": round(actual, 2),
        "rework_hours": round(rework, 2),
        "team_efficiency_percent": kpi.efficiency(planned, actual),
        "team_utilization_percent": kpi.utilization(allocated, available),
        "team_on_time_percent": kpi.on_time_percent(on_time, completed_total),
        "rework_percent": kpi.rework_percent(rework, actual),
        # Counted over the period, like the denominator, rather than summing
        # each release's all-time revision_count against this period's
        # completions.
        "revision_rate_percent": kpi.revision_rate(
            _count(
                db,
                Revision,
                Revision.release_id.in_([r.id for r in releases]) if releases else false(),
                func.date(Revision.created_at).between(date_from, date_to),
            ),
            completed_total,
        ),
        "average_review_turnaround_hours": kpi.average(turnarounds),
        "first_pass_approval_percent": _first_pass_for_tasks(db, task_ids)["percent"],
        "pending_reviews": _count(
            db,
            Review,
            Review.reviewer_id == lead.id,
            Review.status.in_([ReviewStatus.PENDING.value, ReviewStatus.IN_REVIEW.value]),
        ),
        "blocked_tasks": _count(
            db,
            Task,
            Task.team_lead_id == lead.id,
            Task.status == TaskStatus.BLOCKED.value,
        ),
        "overdue_tasks": _count(
            db,
            Task,
            Task.team_lead_id == lead.id,
            Task.status.in_(_OPEN_TASKS),
            Task.planned_end < today,
        ),
        "team_capacity": capacity_rows,
    }


# ---------------------------------------------------------------------------
# Trends
# ---------------------------------------------------------------------------


def monthly_trends(db: Session, months: int = 6) -> list[dict]:
    """Month-by-month output, efficiency, on-time and rework.

    Grouped in SQL by month so the series stays cheap regardless of how many
    tasks the department has completed.
    """
    today = date.today()
    start = (today.replace(day=1) - timedelta(days=31 * (months - 1))).replace(day=1)

    # Build each date_trunc expression once and reuse the same object in both
    # the select list and the GROUP BY. Writing it out twice produces two
    # distinct bind parameters, which Postgres will not treat as the same
    # grouping expression.
    task_bucket = func.date_trunc("month", Task.completed_at)
    release_bucket = func.date_trunc("month", DesignRelease.actual_end)

    completed = db.execute(
        select(
            task_bucket.label("bucket"),
            func.count(),
            func.coalesce(func.sum(Task.estimated_hours), 0),
            func.coalesce(func.sum(Task.actual_hours), 0),
            func.coalesce(func.sum(Task.rework_hours), 0),
            func.coalesce(
                func.sum(
                    case((func.date(Task.completed_at) <= Task.planned_end, 1), else_=0)
                ),
                0,
            ),
            func.coalesce(
                func.sum(case((Task.planned_end.is_not(None), 1), else_=0)), 0
            ),
        )
        .where(
            Task.status.in_(_DONE_TASKS),
            Task.completed_at.is_not(None),
            func.date(Task.completed_at) >= start,
        )
        .group_by(task_bucket)
        .order_by(task_bucket)
    ).all()

    releases = dict(
        db.execute(
            select(release_bucket, func.count())
            .where(
                DesignRelease.status == ReleaseStatus.COMPLETED.value,
                DesignRelease.actual_end.is_not(None),
                DesignRelease.actual_end >= start,
            )
            .group_by(release_bucket)
        ).all()
    )

    series = []
    for bucket, count, planned, actual, rework, on_time, with_dates in completed:
        month = bucket.date() if hasattr(bucket, "date") else bucket
        series.append(
            {
                "month": month.strftime("%Y-%m"),
                "tasks_completed": int(count),
                "releases_completed": int(releases.get(bucket, 0)),
                "planned_hours": round(float(planned), 2),
                "actual_hours": round(float(actual), 2),
                "rework_hours": round(float(rework), 2),
                "efficiency_percent": kpi.efficiency(planned, actual),
                "on_time_percent": kpi.on_time_percent(int(on_time), int(with_dates)),
                "rework_percent": kpi.rework_percent(rework, actual),
            }
        )
    return series


def bottlenecks(db: Session, limit: int = 10) -> dict:
    """Where work is actually stuck (spec section 27)."""
    today = date.today()

    longest_queue = [
        {
            "task_id": str(t.id),
            "code": t.code,
            "name": t.name,
            "assigned_to": t.assigned_to.full_name if t.assigned_to else None,
            "queue_time_hours": kpi.queue_time_hours(t.assigned_at, t.started_at),
        }
        for t in db.execute(
            select(Task)
            .where(Task.assigned_at.is_not(None), Task.started_at.is_not(None))
            .order_by((Task.started_at - Task.assigned_at).desc())
            .limit(limit)
        ).scalars()
    ]

    slowest_reviews = [
        {
            "review_id": str(r.id),
            "code": r.code,
            "task_code": r.task.code if r.task else None,
            "reviewer": r.reviewer.full_name if r.reviewer else None,
            "turnaround_hours": float(r.turnaround_hours or 0),
        }
        for r in db.execute(
            select(Review)
            .where(Review.turnaround_hours.is_not(None))
            .order_by(Review.turnaround_hours.desc())
            .limit(limit)
        ).scalars()
    ]

    blocked = [
        {
            "task_id": str(t.id),
            "code": t.code,
            "name": t.name,
            "assigned_to": t.assigned_to.full_name if t.assigned_to else None,
            "blocker_reason": t.blocker_reason,
            "blocked_since": t.blocked_at.isoformat() if t.blocked_at else None,
        }
        for t in db.execute(
            select(Task)
            .where(Task.status == TaskStatus.BLOCKED.value)
            .order_by(Task.blocked_at.asc().nullslast())
            .limit(limit)
        ).scalars()
    ]

    waiting_on_dependency = [
        {
            "task_id": str(t.id),
            "code": t.code,
            "name": t.name,
            "planned_start": t.planned_start.isoformat() if t.planned_start else None,
        }
        for t in db.execute(
            select(Task)
            .where(
                Task.status.in_([TaskStatus.NOT_STARTED.value, TaskStatus.ASSIGNED.value]),
                Task.planned_start < today,
            )
            .order_by(Task.planned_start.asc())
            .limit(limit)
        ).scalars()
    ]

    return {
        "longest_queue_times": longest_queue,
        "slowest_reviews": slowest_reviews,
        "blocked_tasks": blocked,
        "waiting_to_start": waiting_on_dependency,
    }


# ---------------------------------------------------------------------------
# Insight engine (spec section 46)
# ---------------------------------------------------------------------------


def insights(db: Session, limit: int = 12) -> list[dict]:
    """Exceptions worth a manager's attention, generated from real data.

    Deliberately mixes good news with bad: a dashboard that only ever reports
    problems trains people to ignore it.
    """
    today = date.today()
    found: list[dict] = []

    thresholds = settings_service.capacity_thresholds(db)
    overload_at = float(thresholds.get("high_load", 100))

    window_end = today + timedelta(days=14)
    for row in capacity_service.team_capacity(
        db, [u.id for u in execution_staff(db)], today, window_end
    ):
        util = row["utilization_percent"]
        if util is not None and util > overload_at:
            found.append(
                {
                    "severity": "warning",
                    "code": "resource_overloaded",
                    "message": f"{row['full_name']} is at {util:.0f}% capacity "
                    f"over the next two weeks.",
                    "entity_type": "user",
                    "entity_id": row["user_id"],
                    "value": util,
                }
            )

    for project in db.execute(
        select(Project).where(
            Project.status.in_(_ACTIVE_PROJECTS),
            Project.health.in_([HealthStatus.RED.value, HealthStatus.AMBER.value]),
        )
    ).scalars():
        reasons = "; ".join(
            r.get("message", "") for r in (project.health_reasons or [])
        )
        found.append(
            {
                "severity": "critical" if project.health == "RED" else "warning",
                "code": "project_health",
                "message": f"{project.code} {project.name} is {project.health}"
                + (f": {reasons}" if reasons else ""),
                "entity_type": "project",
                "entity_id": str(project.id),
                "value": project.health,
            }
        )

    # Release types that systematically overrun are a planning problem, not an
    # individual one, so they are surfaced at the type level.
    overruns = db.execute(
        select(
            DesignRelease.release_type,
            func.coalesce(func.sum(DesignRelease.estimated_hours), 0),
            func.coalesce(func.sum(DesignRelease.actual_hours), 0),
            func.count(),
        )
        .where(DesignRelease.status == ReleaseStatus.COMPLETED.value)
        .group_by(DesignRelease.release_type)
    ).all()
    for release_type, planned, actual, count in overruns:
        variance = kpi.effort_variance_percent(planned, actual)
        if variance is not None and variance > 15 and count >= 2:
            found.append(
                {
                    "severity": "warning",
                    "code": "release_type_overrun",
                    "message": f"{release_type} releases are averaging "
                    f"{variance:.0f}% above estimated hours across {count} releases.",
                    "entity_type": "release_type",
                    "entity_id": release_type,
                    "value": round(variance, 2),
                }
            )

    target = float(settings_service.get_setting(db, "kpi.first_pass_target_percent", 85))
    for lead in db.execute(
        select(User)
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(Role.name == "Team Lead", User.is_active.is_(True))
    ).scalars():
        task_ids = [
            row[0]
            for row in db.execute(
                select(Task.id).where(Task.team_lead_id == lead.id)
            ).all()
        ]
        stats = _first_pass_for_tasks(db, task_ids)
        if stats["percent"] is not None and stats["percent"] < target and stats["submitted"] >= 3:
            found.append(
                {
                    "severity": "warning",
                    "code": "low_first_pass",
                    "message": f"{lead.full_name}'s team has a first-pass approval "
                    f"rate of {stats['percent']:.0f}% (target {target:.0f}%).",
                    "entity_type": "user",
                    "entity_id": str(lead.id),
                    "value": stats["percent"],
                }
            )

    for project in db.execute(
        select(Project).where(
            Project.status.in_(_ACTIVE_PROJECTS),
            Project.required_completion_date.is_not(None),
            Project.completion_percent >= 90,
            Project.delay_days == 0,
        )
    ).scalars():
        days_ahead = (project.required_completion_date - today).days
        if days_ahead > 2:
            found.append(
                {
                    "severity": "positive",
                    "code": "ahead_of_schedule",
                    "message": f"{project.code} {project.name} is "
                    f"{project.completion_percent:.0f}% complete with "
                    f"{days_ahead} day(s) still in hand.",
                    "entity_type": "project",
                    "entity_id": str(project.id),
                    "value": days_ahead,
                }
            )

    order = {"critical": 0, "warning": 1, "positive": 2}
    found.sort(key=lambda i: order.get(i["severity"], 3))
    return found[:limit]
