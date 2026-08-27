"""Review and revision workflow (spec sections 16 and 17).

The loop this implements:

    submit -> review -> approve            (done)
                     -> request revision   -> rework -> resubmit -> review

Two measurements depend on getting this exactly right:

* `round_number` distinguishes a first-time approval from one that needed
  rework, which is what makes First-Pass Approval % meaningful.
* A revision's category decides whether the rework was controllable or
  externally caused, so a designer is never penalised for a customer change.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import (
    AuditAction,
    NotificationSeverity,
    ReviewResult,
    ReviewStatus,
    RevisionStatus,
    TaskStatus,
)
from app.core.errors import BusinessRuleError, NotFoundError, ValidationError
from app.models.execution import Review, Revision
from app.models.release import DesignRelease
from app.models.task import Task
from app.models.user import User
from app.services import (
    audit_service,
    code_service,
    kpi,
    notification_service,
    rollup_service,
    settings_service,
    task_service,
)
from app.services.notification_service import Event


def submit_for_review(
    db: Session,
    *,
    task: Task,
    actor: User,
    reviewer_id: uuid.UUID | None = None,
    note: str | None = None,
    delay_reason: str | None = None,
    variance_reason: str | None = None,
    variance_note: str | None = None,
    context: dict | None = None,
) -> Review:
    """Move a task into the review queue and open a review record."""
    task_service.transition(
        db,
        task,
        TaskStatus.SUBMITTED_FOR_REVIEW.value,
        actor=actor,
        note=note,
        delay_reason=delay_reason,
        variance_reason=variance_reason,
        variance_note=variance_note,
        context=context,
    )

    # Default to the release's Team Lead: they own the release, so an
    # unrouted submission still lands in a real person's queue.
    if reviewer_id is None:
        reviewer_id = task.team_lead_id
        if reviewer_id is None:
            release = db.get(DesignRelease, task.release_id)
            reviewer_id = release.team_lead_id if release else None

    round_number = (
        db.execute(
            select(func.coalesce(func.max(Review.round_number), 0)).where(
                Review.task_id == task.id
            )
        ).scalar()
        or 0
    ) + 1

    review = Review(
        code=code_service.next_code(db, "review"),
        task_id=task.id,
        release_id=task.release_id,
        project_id=task.project_id,
        round_number=round_number,
        submitted_by_id=actor.id,
        reviewer_id=reviewer_id,
        submitted_at=datetime.now(UTC),
        status=ReviewStatus.PENDING.value,
        comments=note,
    )
    db.add(review)
    db.flush()

    notification_service.notify(
        db,
        user_id=reviewer_id,
        event_type=Event.REVIEW_PENDING,
        title=f"Review requested: {task.name}",
        body=f"{actor.full_name} submitted {task.code} (round {round_number}).",
        entity_type="task",
        entity_id=task.id,
    )

    audit_service.record(
        db,
        entity_type="review",
        entity_id=review.id,
        entity_code=review.code,
        action=AuditAction.CREATE,
        actor=actor,
        summary=f"Submitted {task.code} for review (round {round_number})",
        context=context,
    )
    return review


def start_review(db: Session, *, review: Review, actor: User) -> Review:
    """Reviewer picks the item up. Separates queue time from review time."""
    if review.status not in {ReviewStatus.PENDING.value, ReviewStatus.IN_REVIEW.value}:
        raise BusinessRuleError("This review is already closed.")

    if review.review_started_at is None:
        review.review_started_at = datetime.now(UTC)
    review.status = ReviewStatus.IN_REVIEW.value
    review.reviewer_id = review.reviewer_id or actor.id

    task = db.get(Task, review.task_id)
    if task is not None and task.status == TaskStatus.SUBMITTED_FOR_REVIEW.value:
        task_service.transition(
            db, task, TaskStatus.UNDER_REVIEW.value, actor=actor, note="Review started"
        )
        task.review_status = ReviewStatus.IN_REVIEW.value

    db.flush()
    return review


def complete_review(
    db: Session,
    *,
    review: Review,
    actor: User,
    result: str,
    comments: str | None = None,
    revision_category: str | None = None,
    revision_reason: str | None = None,
    root_cause: str | None = None,
    context: dict | None = None,
) -> tuple[Review, Revision | None]:
    """Approve, reject or send back for revision.

    Rejection and revision-request are treated identically downstream -- both
    create a Revision and reopen the task -- because both mean the same thing
    operationally: the work must be redone and the hours must be counted as
    rework.
    """
    if review.status in {
        ReviewStatus.APPROVED.value,
        ReviewStatus.REJECTED.value,
        ReviewStatus.REVISION_REQUESTED.value,
    }:
        raise BusinessRuleError("This review has already been completed.")

    task = db.get(Task, review.task_id)
    if task is None:
        raise NotFoundError("The reviewed task no longer exists.")

    if task.assigned_to_id == actor.id:
        raise BusinessRuleError(
            "You cannot review your own work. Route it to another reviewer."
        )

    now = datetime.now(UTC)
    if review.review_started_at is None:
        review.review_started_at = now
    review.reviewed_at = now
    review.reviewer_id = review.reviewer_id or actor.id
    review.result = result
    review.comments = comments or review.comments
    review.turnaround_hours = kpi.review_turnaround_hours(review.submitted_at, now)

    revision: Revision | None = None

    if result == ReviewResult.APPROVED.value:
        review.status = ReviewStatus.APPROVED.value
        task_service.transition(
            db, task, TaskStatus.APPROVED.value, actor=actor, note=comments,
            context=context,
        )
        task_service.transition(
            db, task, TaskStatus.COMPLETED.value, actor=actor, context=context
        )
        notification_service.notify(
            db,
            user_id=task.assigned_to_id,
            event_type=Event.REVIEW_COMPLETED,
            title=f"Approved: {task.name}",
            body=f"{task.code} was approved by {actor.full_name}.",
            entity_type="task",
            entity_id=task.id,
        )
    else:
        review.status = (
            ReviewStatus.REJECTED.value
            if result == ReviewResult.REJECTED.value
            else ReviewStatus.REVISION_REQUESTED.value
        )
        if not revision_category:
            raise ValidationError(
                "A revision category is required when returning work.",
                details={
                    "allowed": [
                        c["value"]
                        for c in settings_service.get_setting(
                            db, "workflow.revision_categories"
                        )
                    ]
                },
            )
        revision = create_revision(
            db,
            task=task,
            actor=actor,
            category=revision_category,
            reason=revision_reason or comments or "Revision requested at review",
            root_cause=root_cause,
            review=review,
            context=context,
        )

    db.flush()
    rollup_service.refresh_chain(db, task)

    audit_service.record(
        db,
        entity_type="review",
        entity_id=review.id,
        entity_code=review.code,
        action=AuditAction.UPDATE,
        actor=actor,
        summary=f"Review {result} for {task.code} (round {review.round_number})",
        new_value={
            "result": result,
            "turnaround_hours": review.turnaround_hours,
        },
        context=context,
    )
    return review, revision


def create_revision(
    db: Session,
    *,
    task: Task,
    actor: User,
    category: str,
    reason: str,
    root_cause: str | None = None,
    description: str | None = None,
    assigned_to_id: uuid.UUID | None = None,
    review: Review | None = None,
    context: dict | None = None,
) -> Revision:
    """Open a revision and put the task back into the designer's hands."""
    accountability = settings_service.accountability_for(
        db, "workflow.revision_categories", category
    )

    revision_number = (
        db.execute(
            select(func.coalesce(func.max(Revision.revision_number), 0)).where(
                Revision.task_id == task.id
            )
        ).scalar()
        or 0
    ) + 1

    revision = Revision(
        code=code_service.next_code(db, "revision"),
        task_id=task.id,
        release_id=task.release_id,
        project_id=task.project_id,
        review_id=review.id if review else None,
        revision_number=revision_number,
        reason=reason,
        category=category,
        accountability=accountability,
        root_cause=root_cause,
        description=description,
        raised_by_id=actor.id,
        assigned_to_id=assigned_to_id or task.assigned_to_id,
        raised_date=datetime.now(UTC),
        status=RevisionStatus.OPEN.value,
    )
    db.add(revision)
    db.flush()

    task.revision_count = int(task.revision_count or 0) + 1
    if task.status != TaskStatus.REVISION_REQUIRED.value:
        task_service.transition(
            db,
            task,
            TaskStatus.REVISION_REQUIRED.value,
            actor=actor,
            note=reason,
            context=context,
        )

    notification_service.notify(
        db,
        user_id=revision.assigned_to_id,
        event_type=Event.REVISION_REQUESTED,
        title=f"Revision required: {task.name}",
        body=f"{category}: {reason}",
        severity=NotificationSeverity.WARNING.value,
        entity_type="task",
        entity_id=task.id,
    )

    audit_service.record(
        db,
        entity_type="revision",
        entity_id=revision.id,
        entity_code=revision.code,
        action=AuditAction.CREATE,
        actor=actor,
        summary=f"Revision {revision_number} raised on {task.code} ({category})",
        new_value={"category": category, "accountability": accountability},
        context=context,
    )

    db.flush()
    rollup_service.refresh_chain(db, task)
    return revision


def resolve_revision(
    db: Session, *, revision: Revision, actor: User, context: dict | None = None
) -> Revision:
    if revision.status == RevisionStatus.RESOLVED.value:
        return revision

    revision.status = RevisionStatus.RESOLVED.value
    revision.resolved_date = datetime.now(UTC)
    rollup_service.refresh_revision_hours(db, revision)
    db.flush()

    audit_service.record(
        db,
        entity_type="revision",
        entity_id=revision.id,
        entity_code=revision.code,
        action=AuditAction.UPDATE,
        actor=actor,
        summary=f"Revision {revision.code} resolved "
        f"({float(revision.additional_hours or 0):.1f}h rework)",
        context=context,
    )
    return revision


def first_pass_stats(db: Session, *, task_ids: list[uuid.UUID] | None = None) -> dict:
    """Counts behind First-Pass Approval %.

    Numerator: reviews approved on round 1. Denominator: distinct tasks that
    have been submitted at least once. Counting reviews instead of tasks in
    the denominator would double-penalise a task that went round three times.
    """
    stmt = select(Review)
    if task_ids is not None:
        if not task_ids:
            return {"submitted": 0, "approved_first_round": 0, "percent": None}
        stmt = stmt.where(Review.task_id.in_(task_ids))

    reviews = db.execute(stmt).scalars().all()
    submitted_tasks = {r.task_id for r in reviews}
    approved_first = {
        r.task_id
        for r in reviews
        if r.round_number == 1 and r.result == ReviewResult.APPROVED.value
    }
    return {
        "submitted": len(submitted_tasks),
        "approved_first_round": len(approved_first),
        "percent": kpi.first_pass_approval_percent(
            len(approved_first), len(submitted_tasks)
        ),
    }
