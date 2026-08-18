"""Time tracking (spec section 15).

Guarantees this module enforces:

* Hours are never negative and never zero-length.
* A user has at most one running timer at a time.
* Manual entries cannot overlap an existing entry for the same person.
* Time logged while a revision is open is automatically flagged as rework, so
  Rework % is measured rather than self-reported.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.enums import TaskStatus, TimeEntrySource
from app.core.errors import BusinessRuleError, NotFoundError, ValidationError
from app.models.execution import TimeEntry
from app.models.task import Task
from app.models.user import User
from app.services import code_service, rollup_service, task_service

#: A single entry longer than this is almost certainly a forgotten timer.
MAX_ENTRY_HOURS = 16.0


def running_timer(db: Session, user_id: uuid.UUID) -> TimeEntry | None:
    return db.execute(
        select(TimeEntry).where(
            TimeEntry.user_id == user_id, TimeEntry.is_running.is_(True)
        )
    ).scalar_one_or_none()


def _overlapping(
    db: Session,
    user_id: uuid.UUID,
    started_at: datetime,
    ended_at: datetime,
    exclude_id: uuid.UUID | None = None,
) -> TimeEntry | None:
    """Any existing entry for this user that intersects [started_at, ended_at).

    Overlap is a real correctness issue, not a nicety: double-counted hours
    inflate actual hours, which deflates efficiency and distorts utilisation
    for that person.
    """
    stmt = select(TimeEntry).where(
        TimeEntry.user_id == user_id,
        TimeEntry.started_at.is_not(None),
        TimeEntry.ended_at.is_not(None),
        and_(TimeEntry.started_at < ended_at, TimeEntry.ended_at > started_at),
    )
    if exclude_id is not None:
        stmt = stmt.where(TimeEntry.id != exclude_id)
    return db.execute(stmt.limit(1)).scalar_one_or_none()


def _validate_hours(hours: float) -> float:
    if hours is None:
        raise ValidationError("Hours are required.")
    if hours < 0:
        raise ValidationError("Hours cannot be negative.")
    if hours == 0:
        raise ValidationError("A time entry must be longer than zero hours.")
    if hours > MAX_ENTRY_HOURS:
        raise ValidationError(
            f"A single time entry cannot exceed {MAX_ENTRY_HOURS} hours. "
            "Split it across days instead."
        )
    return round(float(hours), 2)


def _rework_context(db: Session, task: Task) -> tuple[bool, uuid.UUID | None]:
    """Whether time on this task right now counts as rework, and against what."""
    revision = rollup_service.open_revision_for_task(db, task.id)
    if revision is None:
        return False, None
    return True, revision.id


def start_timer(
    db: Session, *, task: Task, user: User, description: str | None = None
) -> TimeEntry:
    existing = running_timer(db, user.id)
    if existing is not None:
        raise BusinessRuleError(
            "You already have a running timer. Stop it before starting another.",
            details={"running_entry_id": str(existing.id), "task_id": str(existing.task_id)},
        )
    if task.assigned_to_id != user.id:
        raise BusinessRuleError("You can only log time against your own tasks.")

    # Starting the clock starts the task, so the two can never disagree.
    if task.status in {TaskStatus.ASSIGNED.value, TaskStatus.NOT_STARTED.value,
                       TaskStatus.REVISION_REQUIRED.value, TaskStatus.BLOCKED.value}:
        task_service.transition(
            db, task, TaskStatus.IN_PROGRESS.value, actor=user, note="Timer started"
        )

    is_rework, revision_id = _rework_context(db, task)

    entry = TimeEntry(
        code=code_service.next_code(db, "time_entry"),
        task_id=task.id,
        user_id=user.id,
        release_id=task.release_id,
        project_id=task.project_id,
        entry_date=date.today(),
        started_at=datetime.now(UTC),
        hours=0,
        source=TimeEntrySource.TIMER.value,
        is_running=True,
        is_rework=is_rework,
        revision_id=revision_id,
        description=description,
    )
    db.add(entry)
    db.flush()
    return entry


def stop_timer(db: Session, *, user: User, entry_id: uuid.UUID | None = None) -> TimeEntry:
    entry = (
        db.get(TimeEntry, entry_id) if entry_id else running_timer(db, user.id)
    )
    if entry is None or not entry.is_running:
        raise NotFoundError("No running timer found.")
    if entry.user_id != user.id:
        raise BusinessRuleError("You can only stop your own timer.")

    now = datetime.now(UTC)
    started = entry.started_at
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)

    hours = round((now - started).total_seconds() / 3600, 2)
    if hours <= 0:
        hours = 0.01  # a timer stopped instantly still represents real effort
    if hours > MAX_ENTRY_HOURS:
        # A timer left running overnight would otherwise poison every metric
        # that person appears in; cap it and say so in the description.
        hours = MAX_ENTRY_HOURS
        entry.description = (
            (entry.description or "") + f" [auto-capped at {MAX_ENTRY_HOURS}h]"
        ).strip()

    entry.ended_at = now
    entry.hours = hours
    entry.is_running = False
    db.flush()

    task = db.get(Task, entry.task_id)
    if task is not None:
        rollup_service.refresh_chain(db, task)
    return entry


def log_manual(
    db: Session,
    *,
    task: Task,
    user: User,
    entry_date: date,
    hours: float,
    description: str | None = None,
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
    actor: User | None = None,
) -> TimeEntry:
    """Record time after the fact."""
    hours = _validate_hours(hours)

    if entry_date > date.today():
        raise ValidationError("Time cannot be logged against a future date.")

    actor = actor or user
    if task.assigned_to_id != user.id and actor.id == user.id:
        raise BusinessRuleError("You can only log time against your own tasks.")

    # Derive an interval when the caller did not supply one, so overlap
    # detection has something to work with either way.
    if started_at is None:
        started_at = datetime.combine(
            entry_date, datetime.min.time(), tzinfo=UTC
        ) + timedelta(hours=9)
    if ended_at is None:
        ended_at = started_at + timedelta(hours=hours)

    if ended_at < started_at:
        raise ValidationError("The end time cannot be before the start time.")

    clash = _overlapping(db, user.id, started_at, ended_at)
    if clash is not None:
        raise BusinessRuleError(
            "This overlaps an existing time entry.",
            details={
                "conflicting_entry": clash.code,
                "conflicting_task_id": str(clash.task_id),
                "from": clash.started_at.isoformat() if clash.started_at else None,
                "to": clash.ended_at.isoformat() if clash.ended_at else None,
            },
        )

    is_rework, revision_id = _rework_context(db, task)

    entry = TimeEntry(
        code=code_service.next_code(db, "time_entry"),
        task_id=task.id,
        user_id=user.id,
        release_id=task.release_id,
        project_id=task.project_id,
        entry_date=entry_date,
        started_at=started_at,
        ended_at=ended_at,
        hours=hours,
        source=TimeEntrySource.MANUAL.value,
        is_running=False,
        is_rework=is_rework,
        revision_id=revision_id,
        description=description,
    )
    db.add(entry)
    db.flush()

    rollup_service.refresh_chain(db, task)
    if revision_id:
        from app.models.execution import Revision

        revision = db.get(Revision, revision_id)
        if revision is not None:
            rollup_service.refresh_revision_hours(db, revision)
    return entry


def delete_entry(db: Session, *, entry: TimeEntry) -> None:
    task = db.get(Task, entry.task_id)
    db.delete(entry)
    db.flush()
    if task is not None:
        rollup_service.refresh_chain(db, task)
