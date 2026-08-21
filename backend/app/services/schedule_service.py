"""The release window, and what is allowed to happen to it.

A design release carries a target start and end. Its tasks are planned and
their hours allocated *inside* that window -- that is what makes the window
mean anything. Two rules follow, and they pull in opposite directions on
purpose:

* Nothing may be scheduled before the release opens. A task starting before
  its own release is not an aggressive plan, it is a mistake, and accepting it
  makes the release's start date decorative.

* When work genuinely runs past the end, the end moves. A plan that still
  claims a date everyone knows is gone stops being used, and people go back to
  keeping the real dates in their heads.

The second rule is the dangerous one. A target that follows the work is not a
target: judged against it, every release ever delivered arrives exactly on
time. So the originally committed dates are stamped once as a baseline and
never move, delivery is measured against those, and the distance between the
baseline and the current forecast is surfaced rather than buried -- a release
whose end has been pushed three times is telling you something that a single
"on track" would not.

Actual dates are observed, never typed. A release started when its first task
started and finished when its last one finished, whatever the day somebody got
around to pressing Complete.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import AuditAction, OPEN_TASK_STATUSES, TaskStatus
from app.core.errors import ValidationError
from app.models.release import DesignRelease
from app.models.task import Task
from app.models.user import User
from app.services import audit_service

_OPEN_TASK_VALUES = [s.value for s in OPEN_TASK_STATUSES]
_DONE_TASK_VALUES = [TaskStatus.COMPLETED.value, TaskStatus.APPROVED.value]


def stamp_baseline(release: DesignRelease) -> None:
    """Remember the first dates a release was ever given.

    Called wherever planned dates are set. Only ever fills a blank -- once
    committed, the baseline is the one date in this system that nothing is
    allowed to revise, because everything else about delivery is judged
    against it.
    """
    if release.planned_start and release.baseline_planned_start is None:
        release.baseline_planned_start = release.planned_start
    if release.planned_end and release.baseline_planned_end is None:
        release.baseline_planned_end = release.planned_end


def assert_within_window(release: DesignRelease, planned_start: date | None) -> None:
    """A task may not begin before its release does."""
    if planned_start and release.planned_start and planned_start < release.planned_start:
        raise ValidationError(
            f"A task cannot start before {release.code} does "
            f"({release.planned_start.isoformat()}).",
            details={
                "release_planned_start": release.planned_start.isoformat(),
                "task_planned_start": planned_start.isoformat(),
            },
        )


def extend_for_task(
    db: Session,
    release: DesignRelease,
    planned_end: date | None,
    *,
    actor: User | None = None,
    context: dict | None = None,
) -> int:
    """Move the release's end out to cover a task that runs past it.

    Returns how many days it moved, or 0. Recorded in the audit trail with the
    task that caused it, so a date that has drifted can always be traced back
    to the work that drifted it rather than appearing to have changed itself.
    """
    if planned_end is None or release.planned_end is None:
        return 0
    if planned_end <= release.planned_end:
        return 0

    moved = (planned_end - release.planned_end).days
    previous = release.planned_end
    release.planned_end = planned_end
    db.flush()

    audit_service.record(
        db,
        entity_type="design_release",
        entity_id=release.id,
        entity_code=release.code,
        action=AuditAction.UPDATE,
        actor=actor,
        summary=(
            f"Target end moved {moved} day(s), from {previous.isoformat()} to "
            f"{planned_end.isoformat()}, to cover a task planned past it"
        ),
        context=context,
    )
    return moved


def refresh_actual_dates(db: Session, release: DesignRelease) -> None:
    """Observe when the release really started and really finished.

    Both are read off the tasks rather than stamped by a button. A release
    started when someone first started work on it, and finished when the last
    piece of work finished -- not on the day somebody remembered to press
    Complete, which in a busy week can be days later and in a quiet one can be
    the same day as three other releases.

    The end is only filled once nothing is outstanding; a release with work
    still open has not finished, whatever its status says.
    """
    started, finished, open_count = db.execute(
        select(
            func.min(Task.started_at),
            func.max(Task.completed_at),
            func.count().filter(Task.status.in_(_OPEN_TASK_VALUES)),
        ).where(Task.release_id == release.id)
    ).one()

    release.actual_start = started.date() if started else None
    release.actual_end = finished.date() if finished and not open_count else None


def slippage_days(release: DesignRelease) -> int:
    """How far the current forecast has drifted from what was committed."""
    if release.baseline_planned_end is None or release.planned_end is None:
        return 0
    return max((release.planned_end - release.baseline_planned_end).days, 0)
