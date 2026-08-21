"""Design release endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.deps import (
    AccessScope,
    client_context,
    get_current_user,
    get_scope,
    require_permission,
)
from app.core.enums import AuditAction, ReleaseStatus
from app.core.errors import NotFoundError, ValidationError
from app.core.permissions import P
from app.db.session import get_db
from app.models.project import Project
from app.models.release import DesignRelease
from app.models.task import Task
from app.models.user import User
from app.schemas.common import Message, Page
from app.schemas.workflow import (
    ApplyTemplate,
    ReleaseComplete,
    ReleaseCreate,
    ReleaseDetail,
    ReleaseStatusChange,
    ReleaseSummary,
    ReleaseUpdate,
    TaskSummary,
)
from app.services import (
    audit_service,
    code_service,
    kpi,
    release_service,
    schedule_service,
    rollup_service,
    template_service,
)
from app.api.v1.tasks import task_summary

router = APIRouter(prefix="/releases", tags=["releases"])


def _visible(scope: AccessScope):
    stmt = select(DesignRelease)
    if P.RELEASE_VIEW_ALL in scope.permissions:
        return stmt
    user_id = scope.user.id
    task_release_ids = select(Task.release_id).where(
        or_(Task.assigned_to_id == user_id, Task.team_lead_id == user_id)
    )
    return stmt.where(
        or_(
            DesignRelease.team_lead_id == user_id,
            DesignRelease.created_by_id == user_id,
            DesignRelease.id.in_(task_release_ids),
        )
    )


def _get_visible(db: Session, scope: AccessScope, release_id: uuid.UUID) -> DesignRelease:
    release = db.execute(
        _visible(scope).where(DesignRelease.id == release_id)
    ).scalar_one_or_none()
    if release is None:
        raise NotFoundError("Design release not found.")
    return release


def _task_counts(db: Session, release_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not release_ids:
        return {}
    return dict(
        db.execute(
            select(Task.release_id, func.count())
            .where(Task.release_id.in_(release_ids))
            .group_by(Task.release_id)
        ).all()
    )


@router.get("", response_model=Page[ReleaseSummary])
def list_releases(
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_scope),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    project_id: uuid.UUID | None = None,
    team_lead_id: uuid.UUID | None = None,
    status: list[str] | None = Query(None),
    health: list[str] | None = Query(None),
    release_type: str | None = None,
    overdue_only: bool = False,
    search: str | None = None,
    sort: str = Query("sequence_number"),
) -> Page[ReleaseSummary]:
    stmt = _visible(scope)

    if project_id:
        stmt = stmt.where(DesignRelease.project_id == project_id)
    if team_lead_id:
        stmt = stmt.where(DesignRelease.team_lead_id == team_lead_id)
    if status:
        stmt = stmt.where(DesignRelease.status.in_(status))
    if health:
        stmt = stmt.where(DesignRelease.health.in_(health))
    if release_type:
        stmt = stmt.where(DesignRelease.release_type == release_type)
    if overdue_only:
        stmt = stmt.where(DesignRelease.delay_days > 0)
    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(DesignRelease.name.ilike(pattern), DesignRelease.code.ilike(pattern))
        )

    sort_columns = {
        "sequence_number": DesignRelease.sequence_number,
        "created_at": DesignRelease.created_at,
        "name": DesignRelease.name,
        "status": DesignRelease.status,
        "health": DesignRelease.health,
        "planned_end": DesignRelease.planned_end,
        "delay_days": DesignRelease.delay_days,
        "completion_percent": DesignRelease.completion_percent,
    }
    descending = sort.startswith("-")
    column = sort_columns.get(sort.lstrip("-"), DesignRelease.sequence_number)
    stmt = stmt.order_by(column.desc() if descending else column.asc())

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar() or 0
    rows = (
        db.execute(stmt.offset((page - 1) * page_size).limit(page_size)).scalars().all()
    )
    counts = _task_counts(db, [r.id for r in rows])
    items = [ReleaseSummary.from_model(r, counts.get(r.id, 0)) for r in rows]
    return Page.build(items, total, page, page_size)


@router.post("", response_model=ReleaseDetail, status_code=201)
def create_release(
    payload: ReleaseCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(P.RELEASE_CREATE)),
) -> ReleaseDetail:
    project = db.get(Project, payload.project_id)
    if project is None:
        raise NotFoundError("Project not found.")

    # Sequence numbers define the design sequence, so they are allocated
    # server-side by default rather than trusted from the client.
    sequence = payload.sequence_number
    if sequence is None:
        sequence = (
            db.execute(
                select(func.coalesce(func.max(DesignRelease.sequence_number), 0)).where(
                    DesignRelease.project_id == project.id
                )
            ).scalar()
            or 0
        ) + 1
    else:
        clash = db.execute(
            select(DesignRelease.id).where(
                DesignRelease.project_id == project.id,
                DesignRelease.sequence_number == sequence,
            )
        ).first()
        if clash:
            raise ValidationError(
                f"Sequence number {sequence} is already used in this project."
            )

    release = DesignRelease(
        code=code_service.next_code(db, "release"),
        project_id=project.id,
        sequence_number=sequence,
        name=payload.name,
        release_type=payload.release_type,
        description=payload.description,
        product_id=payload.product_id or project.product_id,
        team_lead_id=payload.team_lead_id,
        priority=payload.priority,
        planned_start=payload.planned_start,
        planned_end=payload.planned_end,
        status=ReleaseStatus.DRAFT.value,
        external_id=payload.external_id,
        created_by_id=user.id,
    )
    schedule_service.stamp_baseline(release)
    db.add(release)
    db.flush()

    audit_service.record(
        db,
        entity_type="design_release",
        entity_id=release.id,
        entity_code=release.code,
        action=AuditAction.CREATE,
        actor=user,
        summary=f"Created release {release.code} - {release.name}",
        context=client_context(request),
    )

    if payload.team_lead_id:
        lead = db.get(User, payload.team_lead_id)
        if lead is None:
            raise NotFoundError("The specified Team Lead does not exist.")
        release_service.assign_team_lead(
            db, release, lead, actor=user, context=client_context(request)
        )

    if payload.template_version_id:
        version = template_service.get_version_or_404(db, payload.template_version_id)
        template_service.generate_tasks_for_release(
            db, release, version, actor=user, context=client_context(request)
        )

    rollup_service.refresh_release(db, release)
    rollup_service.refresh_project(db, project)
    return _detail(db, release)


@router.get("/{release_id}", response_model=ReleaseDetail)
def get_release(
    release_id: uuid.UUID,
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_scope),
) -> ReleaseDetail:
    return _detail(db, _get_visible(db, scope, release_id))


@router.patch("/{release_id}", response_model=ReleaseDetail)
def update_release(
    release_id: uuid.UUID,
    payload: ReleaseUpdate,
    request: Request,
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_scope),
    user: User = Depends(require_permission(P.RELEASE_UPDATE)),
) -> ReleaseDetail:
    release = _get_visible(db, scope, release_id)
    tracked = [
        "name", "release_type", "description", "team_lead_id", "priority",
        "planned_start", "planned_end", "delay_reason", "delay_note", "external_id",
    ]
    before = {f: getattr(release, f) for f in tracked}

    updates = payload.model_dump(exclude_unset=True)
    new_lead_id = updates.pop("team_lead_id", "__unset__")
    for field, value in updates.items():
        setattr(release, field, value)

    if release.planned_start and release.planned_end and release.planned_end < release.planned_start:
        raise ValidationError("planned_end cannot be before planned_start.")

    schedule_service.stamp_baseline(release)

    if new_lead_id != "__unset__" and new_lead_id != before["team_lead_id"]:
        if new_lead_id is None:
            release.team_lead_id = None
        else:
            lead = db.get(User, new_lead_id)
            if lead is None:
                raise NotFoundError("The specified Team Lead does not exist.")
            release_service.assign_team_lead(
                db, release, lead, actor=user, context=client_context(request)
            )

    db.flush()
    after = {f: getattr(release, f) for f in tracked}
    audit_service.record_change(
        db,
        entity_type="design_release",
        entity_id=release.id,
        entity_code=release.code,
        before=before,
        after=after,
        actor=user,
        context=client_context(request),
    )
    rollup_service.refresh_release(db, release)
    return _detail(db, release)


@router.post("/{release_id}/assign-lead", response_model=ReleaseDetail)
def assign_lead(
    release_id: uuid.UUID,
    team_lead_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_scope),
    user: User = Depends(require_permission(P.RELEASE_ASSIGN_LEAD)),
) -> ReleaseDetail:
    release = _get_visible(db, scope, release_id)
    lead = db.get(User, team_lead_id)
    if lead is None:
        raise NotFoundError("The specified Team Lead does not exist.")
    release_service.assign_team_lead(
        db, release, lead, actor=user, context=client_context(request)
    )
    return _detail(db, release)


@router.post("/{release_id}/accept", response_model=ReleaseDetail)
def accept_release(
    release_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_scope),
    user: User = Depends(require_permission(P.RELEASE_ACCEPT)),
) -> ReleaseDetail:
    release = _get_visible(db, scope, release_id)
    release_service.accept(db, release, actor=user, context=client_context(request))
    return _detail(db, release)


@router.post("/{release_id}/apply-template", response_model=list[TaskSummary])
def apply_template(
    release_id: uuid.UUID,
    payload: ApplyTemplate,
    request: Request,
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_scope),
    user: User = Depends(require_permission(P.TEMPLATE_APPLY)),
) -> list[TaskSummary]:
    """Generate the release's standard tasks from a published template version."""
    release = _get_visible(db, scope, release_id)
    version = template_service.get_version_or_404(db, payload.template_version_id)
    tasks = template_service.generate_tasks_for_release(
        db, release, version, actor=user, context=client_context(request)
    )
    rollup_service.refresh_release(db, release)
    project = db.get(Project, release.project_id)
    if project is not None:
        rollup_service.refresh_project(db, project)
    return [task_summary(t) for t in tasks]


@router.get("/{release_id}/suggested-template")
def suggested_template(
    release_id: uuid.UUID,
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_scope),
) -> dict:
    """The template version the system would apply, plus the alternatives."""
    release = _get_visible(db, scope, release_id)
    project = db.get(Project, release.project_id)

    product_id = release.product_id or (project.product_id if project else None)
    family_id = None
    if product_id:
        from app.models.catalog import Product

        product = db.get(Product, product_id)
        family_id = product.product_family_id if product else None

    suggestion = template_service.suggest_template(
        db,
        product_id=product_id,
        product_family_id=family_id,
        release_type=release.release_type,
    )
    matches = template_service.find_matching_templates(
        db,
        product_id=product_id,
        product_family_id=family_id,
        release_type=release.release_type,
    )
    return {
        "suggested": (
            {
                "template_id": str(suggestion.template_id),
                "template_name": suggestion.template.name,
                "version_id": str(suggestion.id),
                "version_number": suggestion.version_number,
                "task_count": len(suggestion.tasks),
                "total_estimated_hours": round(
                    sum(float(t.default_estimated_hours or 0) for t in suggestion.tasks), 2
                ),
            }
            if suggestion
            else None
        ),
        "alternatives": [
            {
                "template_id": str(t.id),
                "template_name": t.name,
                "version_id": str(t.current_version.id) if t.current_version else None,
                "version_number": (
                    t.current_version.version_number if t.current_version else None
                ),
            }
            for t in matches
        ],
    }


@router.post("/{release_id}/status", response_model=ReleaseDetail)
def change_status(
    release_id: uuid.UUID,
    payload: ReleaseStatusChange,
    request: Request,
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_scope),
    user: User = Depends(require_permission(P.RELEASE_UPDATE)),
) -> ReleaseDetail:
    release = _get_visible(db, scope, release_id)
    release_service.transition(
        db,
        release,
        payload.status,
        actor=user,
        note=payload.note,
        context=client_context(request),
    )
    return _detail(db, release)


@router.get("/{release_id}/completion-blockers")
def completion_blockers(
    release_id: uuid.UUID,
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_scope),
) -> dict:
    """Mandatory tasks that would force an override on completion."""
    release = _get_visible(db, scope, release_id)
    blockers = rollup_service.release_completion_blockers(db, release)
    return {
        "can_complete_cleanly": not blockers,
        "blocking_tasks": blockers,
    }


@router.post("/{release_id}/complete", response_model=ReleaseDetail)
def complete_release(
    release_id: uuid.UUID,
    payload: ReleaseComplete,
    request: Request,
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_scope),
    user: User = Depends(require_permission(P.RELEASE_COMPLETE)),
) -> ReleaseDetail:
    release = _get_visible(db, scope, release_id)
    release_service.complete(
        db,
        release,
        actor=user,
        can_override=P.RELEASE_OVERRIDE_COMPLETION in user.permission_codes,
        override_reason=payload.override_reason,
        context=client_context(request),
    )
    return _detail(db, release)


@router.get("/{release_id}/tasks", response_model=list[TaskSummary])
def release_tasks(
    release_id: uuid.UUID,
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_scope),
) -> list[TaskSummary]:
    release = _get_visible(db, scope, release_id)
    rows = (
        db.execute(
            select(Task)
            .where(Task.release_id == release.id)
            .order_by(Task.sequence, Task.created_at)
        )
        .scalars()
        .all()
    )
    return [task_summary(t) for t in rows]


@router.delete("/{release_id}", response_model=Message)
def cancel_release(
    release_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_scope),
    user: User = Depends(require_permission(P.RELEASE_UPDATE)),
) -> Message:
    release = _get_visible(db, scope, release_id)
    release_service.transition(
        db,
        release,
        ReleaseStatus.CANCELLED.value,
        actor=user,
        note="Release cancelled",
        context=client_context(request),
    )
    return Message(message=f"Release {release.code} cancelled.")


def _detail(db: Session, release: DesignRelease) -> ReleaseDetail:
    count = (
        db.execute(
            select(func.count()).select_from(Task).where(Task.release_id == release.id)
        ).scalar()
        or 0
    )
    summary = ReleaseSummary.from_model(release, count)
    version = release.template_version
    return ReleaseDetail(
        **summary.model_dump(),
        description=release.description,
        actual_start=release.actual_start,
        actual_end=release.actual_end,
        baseline_planned_start=release.baseline_planned_start,
        baseline_planned_end=release.baseline_planned_end,
        health_reasons=release.health_reasons or [],
        template_version_id=release.template_version_id,
        template_name=version.template.name if version and version.template else None,
        template_version_label=version.label if version else None,
        delay_reason=release.delay_reason,
        delay_note=release.delay_note,
        completion_override_reason=release.completion_override_reason,
        efficiency_percent=kpi.efficiency(release.estimated_hours, release.actual_hours),
        effort_variance=kpi.effort_variance(
            release.estimated_hours, release.actual_hours
        ),
        external_id=release.external_id,
        created_at=release.created_at,
        updated_at=release.updated_at,
    )
