"""Task workflow: the status machine, dependencies and assignment.

Every status change goes through `transition`, which is the only function
allowed to write `Task.status`. That is what guarantees the lifecycle stamps,
status history, audit entry, notifications and roll-ups all happen together
rather than depending on each call site remembering them.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import (
    AuditAction,
    NotificationSeverity,
    ReviewStatus,
    TaskStatus,
)
from app.core.errors import BusinessRuleError, NotFoundError, ValidationError
from app.models.task import Task, TaskDependency, TaskEstimateHistory
from app.models.user import User
from app.services import audit_service, notification_service, settings_service
from app.services.notification_service import Event

# ---------------------------------------------------------------------------
# The state machine
# ---------------------------------------------------------------------------

#: Legal moves. Anything absent from this map is rejected, so an invalid
#: transition is a 409 with a clear message rather than a corrupted row.
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    TaskStatus.NOT_STARTED.value: {
        TaskStatus.ASSIGNED.value,
        TaskStatus.IN_PROGRESS.value,
        TaskStatus.CANCELLED.value,
    },
    TaskStatus.ASSIGNED.value: {
        TaskStatus.IN_PROGRESS.value,
        TaskStatus.BLOCKED.value,
        TaskStatus.NOT_STARTED.value,
        TaskStatus.CANCELLED.value,
    },
    TaskStatus.IN_PROGRESS.value: {
        TaskStatus.BLOCKED.value,
        TaskStatus.SUBMITTED_FOR_REVIEW.value,
        TaskStatus.COMPLETED.value,
        TaskStatus.ASSIGNED.value,
        TaskStatus.CANCELLED.value,
    },
    TaskStatus.BLOCKED.value: {
        TaskStatus.IN_PROGRESS.value,
        TaskStatus.ASSIGNED.value,
        TaskStatus.CANCELLED.value,
    },
    TaskStatus.SUBMITTED_FOR_REVIEW.value: {
        TaskStatus.UNDER_REVIEW.value,
        TaskStatus.IN_PROGRESS.value,
        TaskStatus.CANCELLED.value,
    },
    TaskStatus.UNDER_REVIEW.value: {
        TaskStatus.APPROVED.value,
        TaskStatus.REVISION_REQUIRED.value,
        TaskStatus.CANCELLED.value,
    },
    TaskStatus.REVISION_REQUIRED.value: {
        TaskStatus.IN_PROGRESS.value,
        TaskStatus.CANCELLED.value,
    },
    TaskStatus.APPROVED.value: {
        TaskStatus.COMPLETED.value,
        TaskStatus.REVISION_REQUIRED.value,
    },
    TaskStatus.COMPLETED.value: {TaskStatus.REVISION_REQUIRED.value},
    TaskStatus.CANCELLED.value: set(),
}


def can_transition(current: str, target: str) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, set())


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


def blocking_prerequisites(db: Session, task: Task) -> list[Task]:
    """Incomplete tasks that must finish before this one may start."""
    rows = db.execute(
        select(Task)
        .join(TaskDependency, TaskDependency.depends_on_task_id == Task.id)
        .where(
            TaskDependency.task_id == task.id,
            TaskDependency.is_blocking.is_(True),
            Task.status.not_in(
                [TaskStatus.COMPLETED.value, TaskStatus.APPROVED.value,
                 TaskStatus.CANCELLED.value]
            ),
        )
    ).scalars().all()
    return list(rows)


def would_create_cycle(
    db: Session, task_id: uuid.UUID, depends_on_id: uuid.UUID
) -> bool:
    """Whether adding this edge would close a dependency loop.

    Walks forward from the proposed prerequisite: if `task_id` is reachable,
    the new edge would make the graph cyclic and nothing in it could ever
    start.
    """
    if task_id == depends_on_id:
        return True

    seen: set[uuid.UUID] = set()
    frontier = [depends_on_id]
    while frontier:
        current = frontier.pop()
        if current in seen:
            continue
        seen.add(current)
        if current == task_id:
            return True
        parents = db.execute(
            select(TaskDependency.depends_on_task_id).where(
                TaskDependency.task_id == current
            )
        ).scalars().all()
        frontier.extend(parents)
    return False


def add_dependency(
    db: Session,
    task: Task,
    depends_on_id: uuid.UUID,
    *,
    is_blocking: bool = True,
    actor: User | None = None,
) -> TaskDependency:
    prerequisite = db.get(Task, depends_on_id)
    if prerequisite is None:
        raise NotFoundError("The prerequisite task does not exist.")
    if prerequisite.release_id != task.release_id:
        raise ValidationError(
            "A task can only depend on another task in the same design release."
        )
    if would_create_cycle(db, task.id, depends_on_id):
        raise ValidationError(
            f"Adding this dependency would create a circular chain with "
            f"{prerequisite.code}."
        )

    existing = db.execute(
        select(TaskDependency).where(
            TaskDependency.task_id == task.id,
            TaskDependency.depends_on_task_id == depends_on_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        # The dependency is already there, but the caller may be changing what
        # kind it is -- promoting an advisory link to a hard gate, or relaxing
        # one. Returning it untouched made that a silent no-op: the request
        # succeeded and nothing changed.
        if existing.is_blocking != is_blocking:
            before = existing.is_blocking
            existing.is_blocking = is_blocking
            db.flush()
            audit_service.record(
                db,
                entity_type="task",
                entity_id=task.id,
                entity_code=task.code,
                action=AuditAction.UPDATE,
                actor=actor,
                summary=(
                    f"Dependency on {prerequisite.code} is now "
                    f"{'blocking' if is_blocking else 'advisory'}"
                ),
                old_value={"is_blocking": before},
                new_value={"is_blocking": is_blocking},
            )
        return existing

    dependency = TaskDependency(
        task_id=task.id, depends_on_task_id=depends_on_id, is_blocking=is_blocking
    )
    db.add(dependency)
    db.flush()

    audit_service.record(
        db,
        entity_type="task",
        entity_id=task.id,
        entity_code=task.code,
        action=AuditAction.UPDATE,
        actor=actor,
        summary=f"Added dependency on {prerequisite.code}",
        new_value={"depends_on": prerequisite.code, "is_blocking": is_blocking},
    )
    return dependency


# ---------------------------------------------------------------------------
# Assignment and estimation
# ---------------------------------------------------------------------------


def assign(
    db: Session,
    task: Task,
    assignee: User | None,
    *,
    actor: User | None,
    context: dict | None = None,
) -> Task:
    """Assign or unassign a task, notifying the new owner."""
    previous_id = task.assigned_to_id
    if assignee is not None and previous_id == assignee.id:
        return task

    task.assigned_to_id = assignee.id if assignee else None

    if assignee is not None:
        task.assigned_at = datetime.now(UTC)
        if task.status == TaskStatus.NOT_STARTED.value:
            # Assignment alone moves a fresh task forward; it does not start it.
            _set_status(db, task, TaskStatus.ASSIGNED.value, actor=actor,
                        note="Assigned", context=context)
        notification_service.notify(
            db,
            user_id=assignee.id,
            event_type=Event.TASK_ASSIGNED,
            title=f"Task assigned: {task.name}",
            body=f"{task.code} is due {task.planned_end or 'unscheduled'}.",
            entity_type="task",
            entity_id=task.id,
        )

    audit_service.record(
        db,
        entity_type="task",
        entity_id=task.id,
        entity_code=task.code,
        action=AuditAction.ASSIGN,
        actor=actor,
        summary=f"Assigned to {assignee.full_name}" if assignee else "Unassigned",
        old_value={"assigned_to_id": previous_id},
        new_value={"assigned_to_id": task.assigned_to_id},
        context=context,
    )
    db.flush()
    return task


def re_estimate(
    db: Session,
    task: Task,
    new_hours: float,
    *,
    reason: str | None,
    actor: User | None,
) -> Task:
    """Change a task's estimate without destroying the previous one.

    The original estimate stays in `original_estimated_hours` and each change
    appends to estimate_history, so variance is always measured against the
    plan that was actually committed to (spec section 50).
    """
    if new_hours < 0:
        raise ValidationError("Estimated hours cannot be negative.")

    previous = float(task.estimated_hours or 0)
    if previous == float(new_hours):
        return task

    db.add(
        TaskEstimateHistory(
            task_id=task.id,
            previous_hours=previous,
            new_hours=new_hours,
            reason=reason,
            changed_by_id=actor.id if actor else None,
        )
    )
    task.estimated_hours = new_hours
    db.flush()

    audit_service.record(
        db,
        entity_type="task",
        entity_id=task.id,
        entity_code=task.code,
        action=AuditAction.UPDATE,
        actor=actor,
        summary=f"Re-estimated {previous}h -> {new_hours}h",
        old_value={"estimated_hours": previous},
        new_value={"estimated_hours": new_hours, "reason": reason},
    )
    return task


# ---------------------------------------------------------------------------
# Transitions
# ---------------------------------------------------------------------------


def _set_status(
    db: Session,
    task: Task,
    target: str,
    *,
    actor: User | None,
    note: str | None = None,
    context: dict | None = None,
) -> None:
    """Write the status and its history. Assumes the move is already validated."""
    previous = task.status
    task.status = target
    audit_service.record_status(
        db,
        entity_type="task",
        entity_id=task.id,
        entity_code=task.code,
        from_status=previous,
        to_status=target,
        actor=actor,
        note=note,
        context=context,
    )


def transition(
    db: Session,
    task: Task,
    target: str,
    *,
    actor: User | None,
    note: str | None = None,
    delay_reason: str | None = None,
    context: dict | None = None,
    today: date | None = None,
) -> Task:
    """Move a task to `target`, enforcing every rule that applies.

    Rules enforced here rather than at call sites: legal transitions,
    dependency gating, mandatory delay reasons on overdue work, and the
    lifecycle timestamps the KPI engine depends on.
    """
    today = today or date.today()
    current = task.status

    if current == target:
        return task
    if not can_transition(current, target):
        raise BusinessRuleError(
            f"Cannot move {task.code} from '{current}' to '{target}'.",
            details={
                "current": current,
                "allowed": sorted(ALLOWED_TRANSITIONS.get(current, set())),
            },
        )

    now = datetime.now(UTC)

    if target == TaskStatus.IN_PROGRESS.value:
        blockers = blocking_prerequisites(db, task)
        if blockers:
            raise BusinessRuleError(
                f"{task.code} cannot start until its prerequisites are complete.",
                details={
                    "blocked_by": [
                        {"code": b.code, "name": b.name, "status": b.status}
                        for b in blockers
                    ]
                },
            )
        if task.assigned_to_id is None:
            raise BusinessRuleError(
                f"{task.code} must be assigned before work can start."
            )
        if task.started_at is None:
            # First start only. Resuming after a block or a revision must not
            # reset the clock, or cycle time would under-report every reworked
            # task.
            task.started_at = now
        if current == TaskStatus.BLOCKED.value and task.blocked_at is not None:
            blocked_since = task.blocked_at
            if blocked_since.tzinfo is None:
                blocked_since = blocked_since.replace(tzinfo=UTC)
            task.blocked_hours = round(
                float(task.blocked_hours or 0)
                + (now - blocked_since).total_seconds() / 3600,
                2,
            )
            task.blocked_at = None
            task.blocker_reason = None

    if target == TaskStatus.BLOCKED.value:
        if not note:
            raise ValidationError("A blocker reason is required when blocking a task.")
        task.blocker_reason = note
        task.blocked_at = now
        notification_service.notify(
            db,
            user_id=task.team_lead_id,
            event_type=Event.TASK_BLOCKED,
            title=f"Task blocked: {task.name}",
            body=note,
            severity=NotificationSeverity.WARNING.value,
            entity_type="task",
            entity_id=task.id,
        )

    if target == TaskStatus.SUBMITTED_FOR_REVIEW.value:
        if not task.requires_review:
            raise BusinessRuleError(
                f"{task.code} does not require review; complete it directly."
            )
        task.submitted_at = now
        task.submission_count = int(task.submission_count or 0) + 1
        task.review_status = ReviewStatus.PENDING.value
        task.completion_percent = 100

    if target == TaskStatus.COMPLETED.value:
        if task.requires_review and task.review_status != ReviewStatus.APPROVED.value:
            raise BusinessRuleError(
                f"{task.code} requires review approval before it can be completed."
            )
        task.completed_at = now
        task.completion_percent = 100

    if target == TaskStatus.APPROVED.value:
        task.review_status = ReviewStatus.APPROVED.value
        task.completion_percent = 100

    if target == TaskStatus.REVISION_REQUIRED.value:
        task.review_status = ReviewStatus.REVISION_REQUESTED.value
        task.completed_at = None
        # Reopened work is not 100% done any more; leaving it at 100 would let
        # a reworked release report itself complete.
        task.completion_percent = min(float(task.completion_percent or 0), 90)

    # An overdue item must say why before it moves on, when the rule is on.
    if (
        settings_service.get_setting(db, "workflow.require_delay_reason", True)
        and task.planned_end
        and task.planned_end < today
        and target in {TaskStatus.SUBMITTED_FOR_REVIEW.value, TaskStatus.COMPLETED.value}
        and not (delay_reason or task.delay_reason)
    ):
        raise ValidationError(
            f"{task.code} is past its planned end date; a delay reason is required.",
            details={
                "allowed_reasons": [
                    r["value"]
                    for r in settings_service.get_setting(db, "workflow.delay_reasons")
                ]
            },
        )

    if delay_reason:
        task.delay_reason = delay_reason

    _set_status(db, task, target, actor=actor, note=note, context=context)

    # Downstream work that just became startable is worth telling people about.
    if target in {TaskStatus.COMPLETED.value, TaskStatus.APPROVED.value}:
        _notify_unblocked_dependents(db, task)

    db.flush()
    return task


def _notify_unblocked_dependents(db: Session, task: Task) -> None:
    dependents = db.execute(
        select(Task)
        .join(TaskDependency, TaskDependency.task_id == Task.id)
        .where(TaskDependency.depends_on_task_id == task.id)
    ).scalars().all()

    for dependent in dependents:
        if blocking_prerequisites(db, dependent):
            continue
        notification_service.notify(
            db,
            user_id=dependent.assigned_to_id,
            event_type=Event.TASK_DEPENDENCY_COMPLETED,
            title=f"Ready to start: {dependent.name}",
            body=f"{task.code} is complete, so {dependent.code} is no longer blocked.",
            entity_type="task",
            entity_id=dependent.id,
        )


def get_or_404(db: Session, task_id: uuid.UUID) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise NotFoundError("Task not found.")
    return task
