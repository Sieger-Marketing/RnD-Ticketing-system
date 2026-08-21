"""Delay detection and RAG health (spec sections 20 and 21).

The health engine never returns a bare colour. Every AMBER or RED carries the
list of findings that produced it, because "Project ABC is RED" is not
actionable and "Project ABC is RED: 3 critical tasks overdue, team at 108%,
14 rework hours" is. Findings are structured, not prose, so the frontend can
render them and the insight engine can aggregate them.

All thresholds come from app_settings. Nothing in this module hard-codes a
number that a manager is entitled to disagree with.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import (
    OPEN_TASK_STATUSES,
    HealthStatus,
    Priority,
    ProjectStatus,
    ReleaseStatus,
    TaskStatus,
)
from app.models.project import Project
from app.models.release import DesignRelease
from app.models.task import Task
from app.services import kpi, settings_service

_OPEN_TASK_VALUES = [s.value for s in OPEN_TASK_STATUSES]


class Finding:
    """One reason behind a health rating."""

    def __init__(self, level: str, code: str, message: str, value=None) -> None:
        self.level = level
        self.code = code
        self.message = message
        self.value = value

    def as_dict(self) -> dict:
        return {
            "level": self.level,
            "code": self.code,
            "message": self.message,
            "value": self.value,
        }


def _worst(findings: list[Finding]) -> str:
    if any(f.level == HealthStatus.RED.value for f in findings):
        return HealthStatus.RED.value
    if any(f.level == HealthStatus.AMBER.value for f in findings):
        return HealthStatus.AMBER.value
    return HealthStatus.GREEN.value


def _band(value: float | None, amber: float, red: float) -> str | None:
    """Which band a value falls in, where higher is worse."""
    if value is None:
        return None
    if value >= red:
        return HealthStatus.RED.value
    if value >= amber:
        return HealthStatus.AMBER.value
    return None


# ---------------------------------------------------------------------------
# Delay
# ---------------------------------------------------------------------------


def refresh_task_delay(db: Session, task: Task, today: date | None = None) -> int:
    """Recompute a task's delay in days. Returns the new value."""
    today = today or date.today()
    is_open = task.status in _OPEN_TASK_VALUES
    task.delay_days = kpi.delay_days(task.planned_end, is_open, today)
    return task.delay_days


def overdue_tasks_query(scope_ids: list[uuid.UUID] | None = None, today: date | None = None):
    """Select statement for overdue tasks: past planned end and still open."""
    today = today or date.today()
    stmt = select(Task).where(
        Task.planned_end.is_not(None),
        Task.planned_end < today,
        Task.status.in_(_OPEN_TASK_VALUES),
    )
    if scope_ids is not None:
        stmt = stmt.where(Task.assigned_to_id.in_(scope_ids))
    return stmt


#: A release still running. Approved counts as finished: the drawings are out,
#: and only the formal close remains.
_OPEN_RELEASE_VALUES = [
    s.value
    for s in ReleaseStatus
    if s not in {ReleaseStatus.COMPLETED, ReleaseStatus.CANCELLED, ReleaseStatus.APPROVED}
]

_OPEN_PROJECT_VALUES = [
    s.value
    for s in ProjectStatus
    if s not in {ProjectStatus.COMPLETED, ProjectStatus.CANCELLED}
]


def live_delay_days(
    planned_end: date | None, status: str, open_values: list[str], today: date
) -> int:
    """Days past the planned end, computed now rather than read from a column.

    The stored delay_days columns are only as fresh as the last sweep, and
    nothing in this application runs one on a schedule. A project nobody
    touched would otherwise keep yesterday's delay -- and therefore yesterday's
    colour -- which is the one thing a health indicator must never do. Dates and
    today are enough to answer this, so health asks them directly and the stored
    column stays a convenience for lists and sorting.
    """
    return kpi.delay_days(planned_end, status in open_values, today)


def delivered_late_days(
    actual_end: date | None, planned_end: date | None
) -> int:
    """How late a finished item landed. Zero when it landed on or before time.

    Deliberately not delay_days: that measures an *open* item against today and
    is zero for anything finished, so reading it for a delivered release
    reported every late delivery as on time as soon as a sweep ran.
    """
    variance = kpi.schedule_variance_days(actual_end, planned_end)
    return max(variance, 0) if variance is not None else 0


def sweep_delays(db: Session, today: date | None = None) -> dict[str, int]:
    """Recompute delay_days across tasks, releases and projects.

    Run on a schedule or before a dashboard read. Idempotent: running it twice
    on the same day changes nothing.
    """
    today = today or date.today()
    counts = {"tasks": 0, "releases": 0, "projects": 0}

    for task in db.execute(
        select(Task).where(Task.planned_end.is_not(None))
    ).scalars():
        before = task.delay_days
        if refresh_task_delay(db, task, today) != before:
            counts["tasks"] += 1

    for release in db.execute(
        select(DesignRelease).where(DesignRelease.planned_end.is_not(None))
    ).scalars():
        before = release.delay_days
        release.delay_days = kpi.delay_days(
            release.planned_end, release.status in _OPEN_RELEASE_VALUES, today
        )
        if release.delay_days != before:
            counts["releases"] += 1

    for project in db.execute(
        select(Project).where(Project.required_completion_date.is_not(None))
    ).scalars():
        before = project.delay_days
        is_open = project.status not in {"Completed", "Cancelled"}
        project.delay_days = kpi.delay_days(
            project.required_completion_date, is_open, today
        )
        if project.delay_days != before:
            counts["projects"] += 1

    db.flush()
    return counts


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


def evaluate_release_health(
    db: Session, release: DesignRelease, today: date | None = None
) -> tuple[str, list[dict]]:
    """RAG for a release.

    Live work is weighed on schedule, open blockers, effort and rework.
    Finished work reports its delivery outcome only: whether it landed late.

    The distinction matters because RAG is what a manager scans for things
    that still need attention, and a finished release cannot be acted on.
    Judging one on effort overrun left a project that had delivered two of its
    three releases showing three red bars -- a crisis rather than a record. The
    overrun is not lost: it is already stated precisely as effort variance and
    efficiency, and it still feeds the department KPIs and the insight engine.
    """
    today = today or date.today()
    rules = settings_service.health_rules(db)
    findings: list[Finding] = []

    if release.status in {
        ReleaseStatus.COMPLETED.value,
        ReleaseStatus.CANCELLED.value,
    }:
        # Open-task and blocker findings would be stale by definition here, and
        # effort overrun is reported as a number rather than a colour.
        late_by = delivered_late_days(release.actual_end, release.planned_end)
        if release.status == ReleaseStatus.COMPLETED.value and late_by:
            level = _band(
                late_by,
                float(rules.get("amber_delay_days", 2)),
                float(rules.get("red_delay_days", 5)),
            )
            if level:
                findings.append(
                    Finding(
                        level,
                        "delivered_late",
                        f"Delivered {late_by} day(s) after the planned end",
                        late_by,
                    )
                )
        return _worst(findings), [f.as_dict() for f in findings]

    delay = live_delay_days(
        release.planned_end, release.status, _OPEN_RELEASE_VALUES, today
    )
    if delay:
        level = _band(
            delay,
            float(rules.get("amber_delay_days", 2)),
            float(rules.get("red_delay_days", 5)),
        )
        if level:
            findings.append(
                Finding(
                    level,
                    "release_behind_schedule",
                    f"Release is {delay} day(s) behind schedule",
                    delay,
                )
            )

    overdue = (
        db.execute(
            select(func.count())
            .select_from(Task)
            .where(
                Task.release_id == release.id,
                Task.planned_end < today,
                Task.status.in_(_OPEN_TASK_VALUES),
            )
        ).scalar()
        or 0
    )
    if overdue:
        level = _band(
            overdue,
            float(rules.get("amber_overdue_tasks", 1)),
            float(rules.get("red_overdue_tasks", 3)),
        )
        if level:
            findings.append(
                Finding(level, "overdue_tasks", f"{overdue} task(s) overdue", overdue)
            )

    blocked = (
        db.execute(
            select(func.count())
            .select_from(Task)
            .where(Task.release_id == release.id, Task.status == TaskStatus.BLOCKED.value)
        ).scalar()
        or 0
    )
    if blocked:
        level = _band(
            blocked,
            float(rules.get("amber_blocked_tasks", 1)),
            float(rules.get("red_blocked_tasks", 3)),
        )
        if level:
            findings.append(
                Finding(level, "blocked_tasks", f"{blocked} task(s) blocked", blocked)
            )

    overrun = kpi.effort_variance_percent(release.estimated_hours, release.actual_hours)
    if overrun is not None and overrun > 0:
        level = _band(
            overrun,
            float(rules.get("amber_effort_overrun_percent", 10)),
            float(rules.get("red_effort_overrun_percent", 25)),
        )
        if level:
            findings.append(
                Finding(
                    level,
                    "effort_overrun",
                    f"Effort is {overrun:.0f}% above estimate",
                    round(overrun, 2),
                )
            )

    rework = kpi.rework_percent(release.rework_hours, release.actual_hours)
    if rework is not None and rework > 0:
        level = _band(
            rework,
            float(rules.get("amber_rework_percent", 10)),
            float(rules.get("red_rework_percent", 20)),
        )
        if level:
            findings.append(
                Finding(
                    level,
                    "rework",
                    f"Rework is {rework:.0f}% of logged effort "
                    f"({float(release.rework_hours or 0):.1f}h)",
                    round(rework, 2),
                )
            )

    # A plan that cannot work, said on the day it is made rather than on the
    # day it fails. Task dates are laid out from the release's start when they
    # are generated and nothing has ever checked they fit inside it, so a
    # release due in a week could carry three weeks of work and look no
    # different from a sound one until the dates began passing one by one.
    if release.planned_end and release.id is not None:
        overrunning = db.execute(
            select(func.count())
            .select_from(Task)
            .where(
                Task.release_id == release.id,
                Task.planned_end.is_not(None),
                Task.planned_end > release.planned_end,
                Task.status.in_(_OPEN_TASK_VALUES),
            )
        ).scalar() or 0
        if overrunning:
            findings.append(
                Finding(
                    "AMBER",
                    "tasks_past_release_date",
                    f"{overrunning} task(s) are planned to finish after this "
                    "release is due",
                    overrunning,
                )
            )

    # A near deadline with substantial work left is a warning in its own right,
    # before anything has technically slipped.
    if release.planned_end and release.status not in {
        ReleaseStatus.COMPLETED.value,
        ReleaseStatus.CANCELLED.value,
    }:
        days_left = (release.planned_end - today).days
        proximity = float(rules.get("deadline_proximity_days", 7))
        completion = float(release.completion_percent or 0)
        if 0 <= days_left <= proximity and completion < 75:
            findings.append(
                Finding(
                    HealthStatus.AMBER.value,
                    "deadline_proximity",
                    f"Due in {days_left} day(s) but only {completion:.0f}% complete",
                    days_left,
                )
            )

    return _worst(findings), [f.as_dict() for f in findings]


def evaluate_project_health(
    db: Session, project: Project, today: date | None = None
) -> tuple[str, list[dict]]:
    """Project health, rolling up its releases and adding project-level checks.

    As with a release, a finished project reports how it landed rather than
    raising alarms nobody can act on.
    """
    today = today or date.today()
    rules = settings_service.health_rules(db)
    findings: list[Finding] = []

    if project.status in {
        ProjectStatus.COMPLETED.value,
        ProjectStatus.CANCELLED.value,
    }:
        landed_late_by = delivered_late_days(
            project.actual_completion_date, project.required_completion_date
        )
        if project.status == ProjectStatus.COMPLETED.value and landed_late_by:
            level = _band(
                landed_late_by,
                float(rules.get("amber_delay_days", 2)),
                float(rules.get("red_delay_days", 5)),
            )
            if level:
                findings.append(
                    Finding(
                        level,
                        "delivered_late",
                        f"Delivered {landed_late_by} day(s) after the required date",
                        landed_late_by,
                    )
                )
        return _worst(findings), [f.as_dict() for f in findings]

    project_delay = live_delay_days(
        project.required_completion_date, project.status, _OPEN_PROJECT_VALUES, today
    )
    if project_delay:
        level = _band(
            project_delay,
            float(rules.get("amber_delay_days", 2)),
            float(rules.get("red_delay_days", 5)),
        )
        if level:
            findings.append(
                Finding(
                    level,
                    "project_behind_schedule",
                    f"Project is {project_delay} day(s) past its required date",
                    project_delay,
                )
            )

    # Releases that are themselves late are named individually -- a director
    # needs to know which one, not just that something is wrong.
    # Selected on the dates rather than on the stored delay_days, so a project
    # nobody has touched since its releases slipped still names them.
    late_releases = db.execute(
        select(DesignRelease).where(
            DesignRelease.project_id == project.id,
            DesignRelease.planned_end.is_not(None),
            DesignRelease.planned_end < today,
            DesignRelease.status.in_(_OPEN_RELEASE_VALUES),
        )
    ).scalars().all()
    for release in late_releases:
        release_delay = live_delay_days(
            release.planned_end, release.status, _OPEN_RELEASE_VALUES, today
        )
        level = _band(
            release_delay,
            float(rules.get("amber_delay_days", 2)),
            float(rules.get("red_delay_days", 5)),
        )
        if level:
            findings.append(
                Finding(
                    level,
                    "release_delayed",
                    f"Release {release.code} ({release.name}) is "
                    f"{release_delay} day(s) behind schedule",
                    release_delay,
                )
            )

    # The same question one level up: a release planned to land after the
    # customer's required date is a plan that does not close, however healthy
    # each release looks on its own.
    if project.required_completion_date:
        late_by_plan = db.execute(
            select(DesignRelease).where(
                DesignRelease.project_id == project.id,
                DesignRelease.planned_end.is_not(None),
                DesignRelease.planned_end > project.required_completion_date,
                DesignRelease.status.in_(_OPEN_RELEASE_VALUES),
            )
        ).scalars().all()
        for release in late_by_plan:
            over = (release.planned_end - project.required_completion_date).days
            findings.append(
                Finding(
                    "AMBER",
                    "release_planned_past_project_date",
                    f"Release {release.code} ({release.name}) is planned to "
                    f"finish {over} day(s) after the project is required",
                    over,
                )
            )

    critical_overdue = (
        db.execute(
            select(func.count())
            .select_from(Task)
            .where(
                Task.project_id == project.id,
                Task.planned_end < today,
                Task.status.in_(_OPEN_TASK_VALUES),
                Task.priority.in_([Priority.HIGH.value, Priority.CRITICAL.value]),
            )
        ).scalar()
        or 0
    )
    if critical_overdue:
        level = _band(
            critical_overdue,
            float(rules.get("amber_overdue_tasks", 1)),
            float(rules.get("red_overdue_tasks", 3)),
        )
        if level:
            findings.append(
                Finding(
                    level,
                    "critical_tasks_overdue",
                    f"{critical_overdue} critical task(s) overdue",
                    critical_overdue,
                )
            )

    blocked = (
        db.execute(
            select(func.count())
            .select_from(Task)
            .where(
                Task.project_id == project.id, Task.status == TaskStatus.BLOCKED.value
            )
        ).scalar()
        or 0
    )
    if blocked:
        level = _band(
            blocked,
            float(rules.get("amber_blocked_tasks", 1)),
            float(rules.get("red_blocked_tasks", 3)),
        )
        if level:
            findings.append(
                Finding(level, "blocked_tasks", f"{blocked} task(s) blocked", blocked)
            )

    overrun = kpi.effort_variance_percent(project.planned_hours, project.actual_hours)
    if overrun is not None and overrun > 0:
        level = _band(
            overrun,
            float(rules.get("amber_effort_overrun_percent", 10)),
            float(rules.get("red_effort_overrun_percent", 25)),
        )
        if level:
            findings.append(
                Finding(
                    level,
                    "effort_overrun",
                    f"Effort is {overrun:.0f}% above plan "
                    f"({float(project.actual_hours or 0):.0f}h vs "
                    f"{float(project.planned_hours or 0):.0f}h)",
                    round(overrun, 2),
                )
            )

    rework = kpi.rework_percent(project.rework_hours, project.actual_hours)
    if rework is not None and rework > 0:
        level = _band(
            rework,
            float(rules.get("amber_rework_percent", 10)),
            float(rules.get("red_rework_percent", 20)),
        )
        if level:
            findings.append(
                Finding(
                    level,
                    "rework",
                    f"{float(project.rework_hours or 0):.1f} rework hour(s) generated "
                    f"({rework:.0f}% of effort)",
                    round(rework, 2),
                )
            )

    return _worst(findings), [f.as_dict() for f in findings]


def refresh_health(db: Session, project: Project, today: date | None = None) -> None:
    """Recompute health for a project and each of its releases.

    The stored delay_days columns are brought up to date at the same time. The
    health findings no longer depend on them -- they compute the delay from the
    dates -- but lists, sorting and filters still read the columns, and this is
    the moment we already have the rows in hand.
    """
    today = today or date.today()
    for release in project.releases:
        release.delay_days = kpi.delay_days(
            release.planned_end, release.status in _OPEN_RELEASE_VALUES, today
        )
        release.health, release.health_reasons = evaluate_release_health(
            db, release, today
        )
    project.delay_days = kpi.delay_days(
        project.required_completion_date,
        project.status in _OPEN_PROJECT_VALUES,
        today,
    )
    project.health, project.health_reasons = evaluate_project_health(db, project, today)
    db.flush()
