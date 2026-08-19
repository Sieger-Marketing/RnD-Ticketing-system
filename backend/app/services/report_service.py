"""The three standard reports (spec section 28).

Nothing here computes a metric. Every number comes from ``analytics_service``
or ``kpi``, which is what keeps a figure in the monthly PDF identical to the
same figure on the dashboard -- a report that quietly recalculates is how two
sources of truth appear.

The builders return an ``export_service.Report``; the caller chooses the
format. That separation is deliberate: a builder that knew about PDFs would
start formatting for them, and the CSV would drift.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import (
    OPEN_TASK_STATUSES,
    ReleaseStatus,
    ReviewStatus,
    RevisionStatus,
    TaskStatus,
)
from app.models.execution import Review, Revision
from app.models.project import Project
from app.models.release import DesignRelease
from app.models.task import Task
from app.models.user import User
from app.services import analytics_service, capacity_service, kpi
from app.services.export_service import Report, Section

_OPEN_TASKS = [s.value for s in OPEN_TASK_STATUSES]
_DONE = [TaskStatus.COMPLETED.value, TaskStatus.APPROVED.value]


def _round(value: float | None, digits: int = 1) -> float | None:
    """Round for display without turning "no data" into zero."""
    return None if value is None else round(float(value), digits)


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _week_bounds(anchor: date) -> tuple[date, date]:
    start = anchor - timedelta(days=anchor.weekday())
    return start, start + timedelta(days=6)


def _month_bounds(anchor: date) -> tuple[date, date]:
    start = anchor.replace(day=1)
    next_month = (start + timedelta(days=32)).replace(day=1)
    return start, next_month - timedelta(days=1)


# ---------------------------------------------------------------------------
# Daily
# ---------------------------------------------------------------------------


def daily_report(db: Session, *, on: date | None = None, actor: User | None = None) -> Report:
    """What moved today, and what is stuck (spec section 28)."""
    on = on or date.today()

    completed = db.execute(
        select(Task)
        .where(Task.status.in_(_DONE), func.date(Task.completed_at) == on)
        .order_by(Task.completed_at)
    ).scalars().all()

    overdue = db.execute(
        select(Task)
        .where(
            Task.planned_end.is_not(None),
            Task.planned_end < on,
            Task.status.in_(_OPEN_TASKS),
        )
        .order_by(Task.delay_days.desc())
    ).scalars().all()

    blocked = db.execute(
        select(Task).where(Task.status == TaskStatus.BLOCKED.value)
    ).scalars().all()

    new_releases = db.execute(
        select(DesignRelease)
        .where(func.date(DesignRelease.created_at) == on)
        .order_by(DesignRelease.code)
    ).scalars().all()

    pending_reviews = db.execute(
        select(Review)
        .where(Review.status.in_([ReviewStatus.PENDING.value, ReviewStatus.IN_REVIEW.value]))
        .order_by(Review.submitted_at)
    ).scalars().all()

    open_task_count = db.execute(
        select(func.count()).select_from(Task).where(Task.status.in_(_OPEN_TASKS))
    ).scalar() or 0

    report = Report(
        key="daily",
        title="Daily Design Report",
        period_label=on.strftime("%A, %d %B %Y"),
        generated_at=datetime.now(UTC),
        generated_by=actor.full_name if actor else None,
        summary=[
            ("Tasks completed today", len(completed)),
            ("Tasks still open", int(open_task_count)),
            ("Overdue tasks", len(overdue)),
            ("Blocked tasks", len(blocked)),
            ("Reviews waiting", len(pending_reviews)),
            ("Releases created today", len(new_releases)),
        ],
    )

    report.sections.append(
        Section(
            title="Completed today",
            columns=["Task", "Name", "Project", "Designer", "Estimated", "Actual", "Variance"],
            rows=[
                [
                    t.code,
                    t.name,
                    t.project.code if t.project else None,
                    t.assigned_to.full_name if t.assigned_to else None,
                    _round(t.estimated_hours),
                    _round(t.actual_hours),
                    _round(kpi.effort_variance(t.estimated_hours, t.actual_hours)),
                ]
                for t in completed
            ],
            note="Variance is actual minus estimated hours; positive means over plan.",
        )
    )

    report.sections.append(
        Section(
            title="Overdue",
            columns=["Task", "Name", "Project", "Designer", "Due", "Days late", "Reason"],
            rows=[
                [
                    t.code,
                    t.name,
                    t.project.code if t.project else None,
                    t.assigned_to.full_name if t.assigned_to else None,
                    _iso(t.planned_end),
                    t.delay_days or 0,
                    t.delay_reason,
                ]
                for t in overdue
            ],
            note="An empty reason means nobody has stated one yet.",
        )
    )

    report.sections.append(
        Section(
            title="Blocked",
            columns=["Task", "Name", "Designer", "Blocked since", "Waiting on"],
            rows=[
                [
                    t.code,
                    t.name,
                    t.assigned_to.full_name if t.assigned_to else None,
                    _iso(t.blocked_at.date() if t.blocked_at else None),
                    t.blocker_reason,
                ]
                for t in blocked
            ],
        )
    )

    report.sections.append(
        Section(
            title="Reviews waiting",
            columns=["Review", "Task", "Round", "Reviewer", "Submitted", "Waiting (h)"],
            rows=[
                [
                    r.code,
                    r.task.code if r.task else None,
                    r.round_number,
                    r.reviewer.full_name if r.reviewer else None,
                    _iso(r.submitted_at.date() if r.submitted_at else None),
                    _round(
                        (datetime.now(UTC) - r.submitted_at).total_seconds() / 3600
                        if r.submitted_at
                        else None
                    ),
                ]
                for r in pending_reviews
            ],
            note="A blank reviewer means the review was never routed to anyone.",
        )
    )

    report.sections.append(
        Section(
            title="Releases created today",
            columns=["Release", "Name", "Project", "Team lead", "Planned end"],
            rows=[
                [
                    r.code,
                    r.name,
                    r.project.code if r.project else None,
                    r.team_lead.full_name if r.team_lead else None,
                    _iso(r.planned_end),
                ]
                for r in new_releases
            ],
        )
    )

    return report


# ---------------------------------------------------------------------------
# Weekly
# ---------------------------------------------------------------------------


def weekly_report(db: Session, *, week_of: date | None = None, actor: User | None = None) -> Report:
    """Team productivity for one week (spec section 28)."""
    start, end = _week_bounds(week_of or date.today())
    metrics = analytics_service.department_metrics(db, date_from=start, date_to=end)

    staff = analytics_service.execution_staff(db)
    per_person = [
        analytics_service.designer_metrics(db, person, date_from=start, date_to=end)
        for person in staff
    ]

    releases_completed = db.execute(
        select(DesignRelease)
        .where(
            DesignRelease.status == ReleaseStatus.COMPLETED.value,
            DesignRelease.actual_end.is_not(None),
            DesignRelease.actual_end >= start,
            DesignRelease.actual_end <= end,
        )
        .order_by(DesignRelease.actual_end)
    ).scalars().all()

    revisions = db.execute(
        select(Revision)
        .where(func.date(Revision.raised_date) >= start, func.date(Revision.raised_date) <= end)
        .order_by(Revision.raised_date)
    ).scalars().all()

    report = Report(
        key="weekly",
        title="Weekly Design Report",
        period_label=f"{start.strftime('%d %b')} to {end.strftime('%d %b %Y')}",
        generated_at=datetime.now(UTC),
        generated_by=actor.full_name if actor else None,
        summary=[
            ("Tasks completed", metrics["completed_tasks"]),
            ("Releases completed", len(releases_completed)),
            ("Planned hours", _round(metrics["planned_hours"])),
            ("Actual hours", _round(metrics["actual_hours"])),
            ("Efficiency %", _round(metrics["efficiency_percent"])),
            ("Utilisation %", _round(metrics["utilization_percent"])),
            ("On-time %", _round(metrics["on_time_percent"])),
            ("Rework %", _round(metrics["rework_percent"])),
            ("Revisions raised", len(revisions)),
            ("Overdue tasks", metrics["overdue_tasks"]),
        ],
    )

    report.sections.append(
        Section(
            title="Productivity by designer",
            columns=[
                "Designer",
                "Completed",
                "Planned h",
                "Actual h",
                "Efficiency %",
                "Utilisation %",
                "On-time %",
                "Rework h",
                "First-pass %",
            ],
            rows=[
                [
                    m["user"]["full_name"],
                    m["tasks_completed"],
                    _round(m["planned_hours"]),
                    _round(m["actual_hours"]),
                    _round(m["efficiency_percent"]),
                    _round(m["utilization_percent"]),
                    _round(m["on_time_percent"]),
                    _round(m["rework_hours"]),
                    _round(m["first_pass_approval_percent"]),
                ]
                for m in sorted(per_person, key=lambda x: -x["tasks_completed"])
            ],
            note=(
                "A blank percentage means there was nothing to measure this week, "
                "not zero. Efficiency is planned divided by actual hours."
            ),
        )
    )

    report.sections.append(
        Section(
            title="Releases completed",
            columns=["Release", "Name", "Project", "Team lead", "Estimated", "Actual", "Days late"],
            rows=[
                [
                    r.code,
                    r.name,
                    r.project.code if r.project else None,
                    r.team_lead.full_name if r.team_lead else None,
                    _round(r.estimated_hours),
                    _round(r.actual_hours),
                    r.delay_days or 0,
                ]
                for r in releases_completed
            ],
        )
    )

    report.sections.append(
        Section(
            title="Rework raised",
            columns=["Revision", "Task", "Category", "Accountability", "Raised", "Reason"],
            rows=[
                [
                    rev.code,
                    rev.task.code if rev.task else None,
                    rev.category,
                    rev.accountability,
                    _iso(rev.raised_date.date() if rev.raised_date else None),
                    rev.reason,
                ]
                for rev in revisions
            ],
            note=(
                "Controllable rework is work the department could have avoided; "
                "external rework follows a customer or upstream change."
            ),
        )
    )

    return report


# ---------------------------------------------------------------------------
# Monthly
# ---------------------------------------------------------------------------


def monthly_report(db: Session, *, month_of: date | None = None, actor: User | None = None) -> Report:
    """Management view of a month (spec section 28)."""
    start, end = _month_bounds(month_of or date.today())
    metrics = analytics_service.department_metrics(db, date_from=start, date_to=end)
    trends = analytics_service.monthly_trends(db, months=6)

    leads = analytics_service.team_leads(db)
    lead_rows = [
        analytics_service.team_lead_metrics(db, lead, date_from=start, date_to=end)
        for lead in leads
    ]

    staff = analytics_service.execution_staff(db)
    designer_rows = [
        analytics_service.designer_metrics(db, person, date_from=start, date_to=end)
        for person in staff
    ]

    projects = db.execute(
        select(Project).order_by(Project.code)
    ).scalars().all()

    capacity_rows = capacity_service.team_capacity(
        db, [u.id for u in staff], start, end
    )

    report = Report(
        key="monthly",
        title="Monthly Management Report",
        period_label=start.strftime("%B %Y"),
        generated_at=datetime.now(UTC),
        generated_by=actor.full_name if actor else None,
        summary=[
            ("Active projects", metrics["active_projects"]),
            ("Completed projects", metrics["completed_projects"]),
            ("Tasks completed", metrics["completed_tasks"]),
            ("Overall efficiency %", _round(metrics["efficiency_percent"])),
            ("Utilisation %", _round(metrics["utilization_percent"])),
            ("On-time delivery %", _round(metrics["on_time_percent"])),
            ("Rework %", _round(metrics["rework_percent"])),
            ("First-pass approval %", _round(metrics["first_pass_approval_percent"])),
            ("Average cycle time (h)", _round(metrics["average_cycle_time_hours"])),
            ("Review turnaround (h)", _round(metrics["average_review_turnaround_hours"])),
        ],
    )

    if lead_rows:
        report.sections.append(
            Section(
                title="Team lead performance",
                columns=[
                    "Team lead",
                    "Releases",
                    "Completed",
                    "Delayed",
                    "Team efficiency %",
                    "Team on-time %",
                    "Rework %",
                    "First-pass %",
                    "Review turnaround (h)",
                ],
                rows=[
                    [
                        m["user"]["full_name"],
                        m["releases_assigned"],
                        m["releases_completed"],
                        m["releases_delayed"],
                        _round(m["team_efficiency_percent"]),
                        _round(m["team_on_time_percent"]),
                        _round(m["rework_percent"]),
                        _round(m["first_pass_approval_percent"]),
                        _round(m["average_review_turnaround_hours"]),
                    ]
                    for m in lead_rows
                ],
            )
        )

    report.sections.append(
        Section(
            title="Designer performance",
            columns=[
                "Designer",
                "Completed",
                "Efficiency %",
                "Utilisation %",
                "On-time %",
                "Rework %",
                "First-pass %",
                "Effort-weighted output",
                "Score",
            ],
            rows=[
                [
                    m["user"]["full_name"],
                    m["tasks_completed"],
                    _round(m["efficiency_percent"]),
                    _round(m["utilization_percent"]),
                    _round(m["on_time_percent"]),
                    _round(m["rework_percent"]),
                    _round(m["first_pass_approval_percent"]),
                    _round(m["effort_weighted_output"]),
                    _round(m["performance_score"]["score"], 0),
                ]
                for m in sorted(
                    designer_rows,
                    key=lambda x: -(x["performance_score"]["score"] or -1),
                )
            ],
            note=(
                "Output is weighted by estimated effort and complexity, so one "
                "large task is not scored below several small ones. Components "
                "with no data are excluded from the score rather than counted "
                "as zero."
            ),
        )
    )

    report.sections.append(
        Section(
            title="Project delivery",
            columns=[
                "Project",
                "Name",
                "Customer",
                "Status",
                "Health",
                "Completion %",
                "Planned h",
                "Actual h",
                "Days late",
            ],
            rows=[
                [
                    p.code,
                    p.name,
                    p.customer.name if p.customer else None,
                    p.status,
                    p.health,
                    _round(p.completion_percent, 0),
                    _round(p.planned_hours),
                    _round(p.actual_hours),
                    p.delay_days or 0,
                ]
                for p in projects
            ],
        )
    )

    report.sections.append(
        Section(
            title="Capacity",
            columns=["Person", "Available h", "Allocated h", "Utilisation %", "Band", "Open tasks"],
            rows=[
                [
                    row["full_name"],
                    _round(row["available_hours"]),
                    _round(row["allocated_hours"]),
                    _round(row["utilization_percent"]),
                    row["utilization_band"],
                    row["open_tasks"],
                ]
                for row in capacity_rows
            ],
            note="Bands come from the configured capacity thresholds.",
        )
    )

    report.sections.append(
        Section(
            title="Productivity trend",
            columns=[
                "Month",
                "Tasks completed",
                "Releases completed",
                "Planned h",
                "Actual h",
                "Efficiency %",
                "On-time %",
                "Rework %",
            ],
            rows=[
                [
                    t["month"],
                    t["tasks_completed"],
                    t["releases_completed"],
                    _round(t["planned_hours"]),
                    _round(t["actual_hours"]),
                    _round(t["efficiency_percent"]),
                    _round(t["on_time_percent"]),
                    _round(t["rework_percent"]),
                ]
                for t in trends
            ],
            note="The last six months, for context around the reported month.",
        )
    )

    open_revisions = db.execute(
        select(func.count())
        .select_from(Revision)
        .where(Revision.status.in_([RevisionStatus.OPEN.value, RevisionStatus.IN_PROGRESS.value]))
    ).scalar() or 0
    report.summary.append(("Open revisions", int(open_revisions)))

    return report


BUILDERS = {
    "daily": daily_report,
    "weekly": weekly_report,
    "monthly": monthly_report,
}
