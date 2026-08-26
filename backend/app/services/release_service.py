"""Design release lifecycle (spec section 47, steps 6-16).

The rule that matters most here is completion: a release cannot be marked
complete while mandatory tasks are still open, unless a user holding
`release.override_completion` explicitly overrides it with a reason. The
override is recorded on the release *and* in the audit log, so a forced
completion is never invisible (spec section 42).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import (
    AuditAction,
    NotificationSeverity,
    ProjectStatus,
    ReleaseStatus,
    TaskStatus,
)
from app.core.errors import BusinessRuleError, NotFoundError, ValidationError
from app.models.project import Project
from app.models.release import DesignRelease
from app.models.task import Task
from app.models.user import User
from app.services import (
    audit_service,
    notification_service,
    rollup_service,
)
from app.services.notification_service import Event

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    ReleaseStatus.DRAFT.value: {
        ReleaseStatus.ASSIGNED.value,
        ReleaseStatus.PLANNING.value,
        ReleaseStatus.CANCELLED.value,
    },
    ReleaseStatus.ASSIGNED.value: {
        ReleaseStatus.PLANNING.value,
        ReleaseStatus.IN_PROGRESS.value,
        ReleaseStatus.ON_HOLD.value,
        ReleaseStatus.CANCELLED.value,
    },
    ReleaseStatus.PLANNING.value: {
        ReleaseStatus.ASSIGNED.value,
        ReleaseStatus.IN_PROGRESS.value,
        ReleaseStatus.ON_HOLD.value,
        ReleaseStatus.CANCELLED.value,
    },
    ReleaseStatus.IN_PROGRESS.value: {
        ReleaseStatus.INTERNAL_REVIEW.value,
        ReleaseStatus.REVISION.value,
        ReleaseStatus.COMPLETED.value,
        ReleaseStatus.ON_HOLD.value,
        ReleaseStatus.CANCELLED.value,
    },
    ReleaseStatus.INTERNAL_REVIEW.value: {
        ReleaseStatus.REVISION.value,
        ReleaseStatus.APPROVED.value,
        ReleaseStatus.IN_PROGRESS.value,
        ReleaseStatus.COMPLETED.value,
    },
    ReleaseStatus.REVISION.value: {
        ReleaseStatus.IN_PROGRESS.value,
        ReleaseStatus.INTERNAL_REVIEW.value,
        ReleaseStatus.CANCELLED.value,
    },
    ReleaseStatus.APPROVED.value: {ReleaseStatus.COMPLETED.value},
    ReleaseStatus.ON_HOLD.value: {
        ReleaseStatus.IN_PROGRESS.value,
        ReleaseStatus.PLANNING.value,
        ReleaseStatus.CANCELLED.value,
    },
    ReleaseStatus.COMPLETED.value: {ReleaseStatus.REVISION.value},
    ReleaseStatus.CANCELLED.value: set(),
}


def can_transition(current: str, target: str) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, set())


def _set_status(
    db: Session,
    release: DesignRelease,
    target: str,
    *,
    actor: User | None,
    note: str | None = None,
    context: dict | None = None,
) -> None:
    previous = release.status
    release.status = target
    audit_service.record_status(
        db,
        entity_type="design_release",
        entity_id=release.id,
        entity_code=release.code,
        from_status=previous,
        to_status=target,
        actor=actor,
        note=note,
        context=context,
    )


def transition(
    db: Session,
    release: DesignRelease,
    target: str,
    *,
    actor: User | None,
    note: str | None = None,
    context: dict | None = None,
) -> DesignRelease:
    if release.status == target:
        return release
    if not can_transition(release.status, target):
        raise BusinessRuleError(
            f"Cannot move release {release.code} from '{release.status}' to '{target}'.",
            details={
                "current": release.status,
                "allowed": sorted(ALLOWED_TRANSITIONS.get(release.status, set())),
            },
        )
    _set_status(db, release, target, actor=actor, note=note, context=context)
    db.flush()
    return release


def assign_team_lead(
    db: Session,
    release: DesignRelease,
    lead: User,
    *,
    actor: User | None,
    context: dict | None = None,
) -> DesignRelease:
    previous = release.team_lead_id
    release.team_lead_id = lead.id

    # Tasks that have not been individually routed follow the release's lead,
    # so reassigning a release does not orphan its review queue.
    db.execute(
        select(Task).where(Task.release_id == release.id)
    )  # ensure identity map is populated before bulk edit
    for task in db.execute(
        select(Task).where(Task.release_id == release.id)
    ).scalars():
        if task.team_lead_id in (None, previous):
            task.team_lead_id = lead.id

    if release.status == ReleaseStatus.DRAFT.value:
        _set_status(
            db, release, ReleaseStatus.ASSIGNED.value, actor=actor, context=context
        )

    notification_service.notify(
        db,
        user_id=lead.id,
        event_type=Event.RELEASE_ASSIGNED,
        title=f"Release assigned: {release.name}",
        body=f"{release.code} is due {release.planned_end or 'unscheduled'}.",
        entity_type="release",
        entity_id=release.id,
    )
    audit_service.record(
        db,
        entity_type="design_release",
        entity_id=release.id,
        entity_code=release.code,
        action=AuditAction.ASSIGN,
        actor=actor,
        summary=f"Team Lead set to {lead.full_name}",
        old_value={"team_lead_id": previous},
        new_value={"team_lead_id": lead.id},
        context=context,
    )
    db.flush()
    return release


def accept(
    db: Session, release: DesignRelease, *, actor: User, context: dict | None = None
) -> DesignRelease:
    """Team Lead takes ownership and moves the release into planning."""
    if release.team_lead_id != actor.id:
        raise BusinessRuleError("Only the assigned Team Lead can accept this release.")
    return transition(
        db,
        release,
        ReleaseStatus.PLANNING.value,
        actor=actor,
        note="Accepted by Team Lead",
        context=context,
    )


def complete(
    db: Session,
    release: DesignRelease,
    *,
    actor: User,
    can_override: bool = False,
    override_reason: str | None = None,
    context: dict | None = None,
    today: date | None = None,
) -> DesignRelease:
    """Complete a release, refusing to do so while mandatory work is open."""
    today = today or date.today()
    blockers = rollup_service.release_completion_blockers(db, release)

    if blockers and not can_override:
        raise BusinessRuleError(
            f"Release {release.code} has {len(blockers)} incomplete mandatory task(s).",
            details={"blocking_tasks": blockers},
        )

    if blockers and can_override:
        if not override_reason:
            raise ValidationError(
                "An override reason is required to complete a release with "
                "incomplete mandatory tasks."
            )
        release.completion_override_by_id = actor.id
        release.completion_override_reason = override_reason
        audit_service.record(
            db,
            entity_type="design_release",
            entity_id=release.id,
            entity_code=release.code,
            action=AuditAction.OVERRIDE,
            actor=actor,
            summary=f"Completed with {len(blockers)} open mandatory task(s): "
            f"{override_reason}",
            new_value={"blocking_tasks": blockers, "reason": override_reason},
            context=context,
        )

    _set_status(
        db, release, ReleaseStatus.COMPLETED.value, actor=actor, context=context
    )
    release.actual_end = today
    db.flush()

    rollup_service.refresh_release(db, release, today)
    project = db.get(Project, release.project_id)
    if project is not None:
        rollup_service.refresh_project(db, project, today)
        _maybe_complete_project(db, project, actor=actor, context=context, today=today)

    notification_service.notify(
        db,
        user_id=project.team_lead_id if project else None,
        event_type=Event.RELEASE_COMPLETED,
        title=f"Release completed: {release.name}",
        body=f"{release.code} closed at {float(release.actual_hours or 0):.1f}h "
        f"against {float(release.estimated_hours or 0):.1f}h planned.",
        entity_type="release",
        entity_id=release.id,
    )
    return release


def _maybe_complete_project(
    db: Session,
    project: Project,
    *,
    actor: User,
    context: dict | None,
    today: date,
) -> None:
    """Close the project once every release is finished.

    Deliberately automatic: the project is a container for its releases, so
    requiring a separate manual close would just let finished projects sit in
    the active list and distort every department metric.
    """
    releases = db.execute(
        select(DesignRelease).where(DesignRelease.project_id == project.id)
    ).scalars().all()
    if not releases:
        return

    open_releases = [
        r
        for r in releases
        if r.status
        not in {ReleaseStatus.COMPLETED.value, ReleaseStatus.CANCELLED.value}
    ]
    if open_releases:
        return

    previous = project.status
    project.status = ProjectStatus.COMPLETED.value
    project.actual_completion_date = today
    project.completion_percent = 100
    db.flush()

    audit_service.record_status(
        db,
        entity_type="project",
        entity_id=project.id,
        entity_code=project.code,
        from_status=previous,
        to_status=project.status,
        actor=actor,
        note="All design releases completed",
        context=context,
    )
    notification_service.notify(
        db,
        user_id=project.team_lead_id,
        event_type="project.completed",
        title=f"Project completed: {project.name}",
        body=f"{project.code} finished with all releases closed.",
        entity_type="project",
        entity_id=project.id,
    )


def flag_at_risk(db: Session, release: DesignRelease) -> None:
    """Tell the Team Lead when a release turns amber or red."""
    if release.health == "GREEN" or release.team_lead_id is None:
        return
    reasons = "; ".join(r.get("message", "") for r in (release.health_reasons or []))
    notification_service.notify(
        db,
        user_id=release.team_lead_id,
        event_type=Event.RELEASE_AT_RISK,
        title=f"Release at risk: {release.name}",
        body=reasons or f"{release.code} is {release.health}.",
        severity=(
            NotificationSeverity.CRITICAL.value
            if release.health == "RED"
            else NotificationSeverity.WARNING.value
        ),
        entity_type="release",
        entity_id=release.id,
    )


def get_or_404(db: Session, release_id: uuid.UUID) -> DesignRelease:
    release = db.get(DesignRelease, release_id)
    if release is None:
        raise NotFoundError("Design release not found.")
    return release
