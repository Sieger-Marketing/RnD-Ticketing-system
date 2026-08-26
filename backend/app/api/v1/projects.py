"""Project endpoints."""

from __future__ import annotations

import uuid
from datetime import date

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
from app.core.enums import AuditAction, ProjectStatus
from app.core.errors import NotFoundError, PermissionDeniedError, ValidationError
from app.core.permissions import P
from app.db.session import get_db
from app.models.project import Project, ProjectMember
from app.models.release import DesignRelease
from app.models.task import Task
from app.models.user import User
from app.schemas.common import Message, Page
from app.schemas.workflow import (
    ProjectCreate,
    ProjectDetail,
    ProjectSummary,
    ProjectUpdate,
)
from app.services import audit_service, code_service, kpi, rollup_service

router = APIRouter(prefix="/projects", tags=["projects"])


def _visible_projects(scope: AccessScope):
    """Restrict the project list to what the caller may see.

    A Director or Manager sees the department. Everyone else sees projects
    they manage, are a member of, or have a task on -- which is what makes a
    Designer's project list meaningful rather than empty or total.
    """
    stmt = select(Project)
    if P.PROJECT_VIEW_ALL in scope.permissions:
        return stmt

    user_id = scope.user.id
    member_ids = select(ProjectMember.project_id).where(ProjectMember.user_id == user_id)
    task_ids = select(Task.project_id).where(
        or_(Task.assigned_to_id == user_id, Task.team_lead_id == user_id)
    )
    release_ids = select(DesignRelease.project_id).where(
        DesignRelease.team_lead_id == user_id
    )
    return stmt.where(
        or_(
            Project.design_manager_id == user_id,
            Project.project_manager_id == user_id,
            Project.team_lead_id == user_id,
            Project.created_by_id == user_id,
            Project.id.in_(member_ids),
            Project.id.in_(task_ids),
            Project.id.in_(release_ids),
        )
    )


def _counts(db: Session, project_ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple[int, int]]:
    """Release and task counts for a page of projects, in two queries.

    Counting per row would turn a 25-item page into 50 extra round trips.
    """
    if not project_ids:
        return {}
    releases = dict(
        db.execute(
            select(DesignRelease.project_id, func.count())
            .where(DesignRelease.project_id.in_(project_ids))
            .group_by(DesignRelease.project_id)
        ).all()
    )
    tasks = dict(
        db.execute(
            select(Task.project_id, func.count())
            .where(Task.project_id.in_(project_ids))
            .group_by(Task.project_id)
        ).all()
    )
    return {pid: (releases.get(pid, 0), tasks.get(pid, 0)) for pid in project_ids}


def _get_visible(db: Session, scope: AccessScope, project_id: uuid.UUID) -> Project:
    project = db.execute(
        _visible_projects(scope).where(Project.id == project_id)
    ).scalar_one_or_none()
    if project is None:
        # Existing-but-hidden and non-existent both return 404 so the endpoint
        # cannot be used to probe which project codes exist.
        raise NotFoundError("Project not found.")
    return project


@router.get("", response_model=Page[ProjectSummary])
def list_projects(
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_scope),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    status: list[str] | None = Query(None),
    health: list[str] | None = Query(None),
    priority: list[str] | None = Query(None),
    customer_id: uuid.UUID | None = None,
    product_id: uuid.UUID | None = None,
    design_manager_id: uuid.UUID | None = None,
    team_lead_id: uuid.UUID | None = None,
    overdue_only: bool = False,
    search: str | None = None,
    sort: str = Query("-created_at"),
) -> Page[ProjectSummary]:
    stmt = _visible_projects(scope)

    if status:
        stmt = stmt.where(Project.status.in_(status))
    if health:
        stmt = stmt.where(Project.health.in_(health))
    if priority:
        stmt = stmt.where(Project.priority.in_(priority))
    if customer_id:
        stmt = stmt.where(Project.customer_id == customer_id)
    if product_id:
        stmt = stmt.where(Project.product_id == product_id)
    if design_manager_id:
        stmt = stmt.where(Project.design_manager_id == design_manager_id)
    if team_lead_id:
        stmt = stmt.where(Project.team_lead_id == team_lead_id)
    if overdue_only:
        stmt = stmt.where(Project.delay_days > 0)
    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                Project.name.ilike(pattern),
                Project.code.ilike(pattern),
                Project.sales_order.ilike(pattern),
                Project.work_order.ilike(pattern),
            )
        )

    sort_columns = {
        "created_at": Project.created_at,
        "name": Project.name,
        "code": Project.code,
        "status": Project.status,
        "health": Project.health,
        "priority": Project.priority,
        "completion_percent": Project.completion_percent,
        "delay_days": Project.delay_days,
        "required_completion_date": Project.required_completion_date,
    }
    descending = sort.startswith("-")
    column = sort_columns.get(sort.lstrip("-"), Project.created_at)
    stmt = stmt.order_by(column.desc() if descending else column.asc())

    total = db.execute(
        select(func.count()).select_from(stmt.subquery())
    ).scalar() or 0

    rows = (
        db.execute(stmt.offset((page - 1) * page_size).limit(page_size))
        .scalars()
        .all()
    )
    counts = _counts(db, [r.id for r in rows])
    items = [
        ProjectSummary.from_model(r, *counts.get(r.id, (0, 0))) for r in rows
    ]
    return Page.build(items, total, page, page_size)


@router.post("", response_model=ProjectDetail, status_code=201)
def create_project(
    payload: ProjectCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(P.PROJECT_CREATE)),
) -> ProjectDetail:
    project = Project(
        code=code_service.next_code(db, "project"),
        name=payload.name,
        description=payload.description,
        customer_id=payload.customer_id,
        product_id=payload.product_id,
        project_type=payload.project_type,
        sales_order=payload.sales_order,
        work_order=payload.work_order,
        project_manager_id=payload.project_manager_id,
        # Default the design manager to whoever created it, since in practice
        # the manager creating a project is the one who will run it.
        design_manager_id=payload.design_manager_id or user.id,
        team_lead_id=payload.team_lead_id,
        priority=payload.priority,
        start_date=payload.start_date,
        required_completion_date=payload.required_completion_date,
        internal_deadline=payload.internal_deadline,
        customer_deadline=payload.customer_deadline,
        status=ProjectStatus.NOT_STARTED.value,
        external_id=payload.external_id,
        created_by_id=user.id,
    )
    db.add(project)
    db.flush()

    audit_service.record(
        db,
        entity_type="project",
        entity_id=project.id,
        entity_code=project.code,
        action=AuditAction.CREATE,
        actor=user,
        summary=f"Created project {project.code} - {project.name}",
        new_value={"name": project.name, "status": project.status},
        context=client_context(request),
    )
    db.flush()
    return _detail(db, project, 0, 0)


@router.get("/{project_id}", response_model=ProjectDetail)
def get_project(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_scope),
) -> ProjectDetail:
    project = _get_visible(db, scope, project_id)
    counts = _counts(db, [project.id]).get(project.id, (0, 0))
    return _detail(db, project, *counts)


@router.patch("/{project_id}", response_model=ProjectDetail)
def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdate,
    request: Request,
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_scope),
    user: User = Depends(require_permission(P.PROJECT_UPDATE)),
) -> ProjectDetail:
    project = _get_visible(db, scope, project_id)

    tracked = [
        "name", "description", "customer_id", "product_id", "project_type",
        "sales_order", "work_order", "project_manager_id", "design_manager_id",
        "team_lead_id",
        "priority", "status", "start_date", "required_completion_date",
        "internal_deadline", "customer_deadline", "external_id",
    ]
    before = {f: getattr(project, f) for f in tracked}

    updates = payload.model_dump(exclude_unset=True)
    if "status" in updates and updates["status"] not in {s.value for s in ProjectStatus}:
        raise ValidationError(f"Unknown project status '{updates['status']}'.")

    for field, value in updates.items():
        setattr(project, field, value)

    start = project.start_date
    end = project.required_completion_date
    if start and end and end < start:
        raise ValidationError(
            "The required completion date cannot be before the start date."
        )

    db.flush()
    after = {f: getattr(project, f) for f in tracked}
    audit_service.record_change(
        db,
        entity_type="project",
        entity_id=project.id,
        entity_code=project.code,
        before=before,
        after=after,
        actor=user,
        context=client_context(request),
    )

    rollup_service.refresh_project(db, project)
    counts = _counts(db, [project.id]).get(project.id, (0, 0))
    return _detail(db, project, *counts)


@router.delete("/{project_id}", response_model=Message)
def cancel_project(
    project_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_scope),
    user: User = Depends(require_permission(P.PROJECT_DELETE)),
) -> Message:
    """Cancel rather than delete.

    Hard-deleting a project would take its releases, tasks, time entries and
    audit history with it, destroying exactly the history the analytics and
    AI-readiness requirements depend on.
    """
    project = _get_visible(db, scope, project_id)
    previous = project.status
    project.status = ProjectStatus.CANCELLED.value
    db.flush()

    audit_service.record_status(
        db,
        entity_type="project",
        entity_id=project.id,
        entity_code=project.code,
        from_status=previous,
        to_status=project.status,
        actor=user,
        note="Project cancelled",
        context=client_context(request),
    )
    return Message(message=f"Project {project.code} cancelled.")


@router.post("/{project_id}/refresh", response_model=ProjectDetail)
def refresh_project(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_scope),
    user: User = Depends(get_current_user),
) -> ProjectDetail:
    """Recompute roll-ups and health for one project."""
    project = _get_visible(db, scope, project_id)
    rollup_service.refresh_project(db, project, date.today())
    counts = _counts(db, [project.id]).get(project.id, (0, 0))
    return _detail(db, project, *counts)


def _detail(
    db: Session, project: Project, release_count: int, task_count: int
) -> ProjectDetail:
    summary = ProjectSummary.from_model(project, release_count, task_count)
    return ProjectDetail(
        **summary.model_dump(),
        description=project.description,
        sales_order=project.sales_order,
        work_order=project.work_order,
        internal_deadline=project.internal_deadline,
        customer_deadline=project.customer_deadline,
        actual_completion_date=project.actual_completion_date,
        health_reasons=project.health_reasons or [],
        external_id=project.external_id,
        created_at=project.created_at,
        updated_at=project.updated_at,
        efficiency_percent=kpi.efficiency(project.planned_hours, project.actual_hours),
        effort_variance=kpi.effort_variance(project.planned_hours, project.actual_hours),
    )
