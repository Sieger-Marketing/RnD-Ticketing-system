"""Task endpoints, including the Kanban board and dependency management."""

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
    require_any_permission,
    require_permission,
)
from app.core.enums import (
    KANBAN_COLUMNS,
    OPEN_TASK_STATUSES,
    AuditAction,
    TaskStatus,
)
from app.core.errors import BusinessRuleError, NotFoundError, ValidationError
from app.core.permissions import P
from app.db.session import get_db
from app.models.project import Project
from app.models.release import DesignRelease
from app.models.task import Task, TaskDependency
from app.models.user import User
from app.schemas.common import Message, Page
from app.schemas.workflow import (
    DependencyIn,
    DependencyOut,
    KanbanBoard,
    KanbanColumn,
    TaskAssign,
    TaskCreate,
    TaskDetail,
    TaskEstimate,
    TaskStatusChange,
    TaskSummary,
    TaskUpdate,
)
from app.services import (
    audit_service,
    code_service,
    deletion_service,
    kpi,
    rollup_service,
    schedule_service,
    settings_service,
    task_service,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])

_OPEN_VALUES = [s.value for s in OPEN_TASK_STATUSES]
_SATISFIED = {TaskStatus.COMPLETED.value, TaskStatus.APPROVED.value,
              TaskStatus.CANCELLED.value}


def task_summary(task: Task, today: date | None = None) -> TaskSummary:
    today = today or date.today()
    return TaskSummary(
        id=task.id,
        code=task.code,
        project_id=task.project_id,
        project_code=task.project.code if task.project else None,
        # Same relationship the code comes from, so this costs no extra query.
        project_name=task.project.name if task.project else None,
        release_id=task.release_id,
        release_code=task.release.code if task.release else None,
        release_name=task.release.name if task.release else None,
        name=task.name,
        task_type=task.task_type,
        status=task.status,
        review_status=task.review_status,
        priority=task.priority,
        complexity=task.complexity,
        is_mandatory=task.is_mandatory,
        requires_review=task.requires_review,
        completion_percent=float(task.completion_percent or 0),
        estimated_hours=float(task.estimated_hours or 0),
        actual_hours=float(task.actual_hours or 0),
        rework_hours=float(task.rework_hours or 0),
        revision_count=task.revision_count or 0,
        delay_days=task.delay_days or 0,
        is_overdue=kpi.is_overdue(task.planned_end, task.status in _OPEN_VALUES, today),
        planned_start=task.planned_start,
        planned_end=task.planned_end,
        assigned_to_id=task.assigned_to_id,
        assigned_to_name=task.assigned_to.full_name if task.assigned_to else None,
        required_skill_name=task.required_skill.name if task.required_skill else None,
        blocker_reason=task.blocker_reason,
    )


def _visible(scope: AccessScope):
    """Task visibility: everything, the caller's team, or only their own."""
    stmt = select(Task)
    if P.TASK_VIEW_ALL in scope.permissions:
        return stmt
    user_id = scope.user.id
    if P.TASK_VIEW_TEAM in scope.permissions:
        report_ids = [u.id for u in scope.user.direct_reports] + [user_id]
        # Leading the project or the release is enough to see the work inside
        # it. Without this a lead could open a project they own, open a release
        # on it, and then be told its tasks belong to another team -- the same
        # contradiction releases had, one level down. It bites hardest exactly
        # where reporting lines are thin: with no direct reports, the first
        # clause matches nothing and a lead sees only tasks stamped with their
        # own id.
        led_projects = select(Project.id).where(Project.team_lead_id == user_id)
        led_releases = select(DesignRelease.id).where(
            DesignRelease.team_lead_id == user_id
        )
        return stmt.where(
            or_(
                Task.assigned_to_id.in_(report_ids),
                Task.team_lead_id == user_id,
                Task.created_by_id == user_id,
                Task.project_id.in_(led_projects),
                Task.release_id.in_(led_releases),
            )
        )
    return stmt.where(
        or_(Task.assigned_to_id == user_id, Task.created_by_id == user_id)
    )


def _get_visible(db: Session, scope: AccessScope, task_id: uuid.UUID) -> Task:
    task = db.execute(_visible(scope).where(Task.id == task_id)).scalar_one_or_none()
    if task is None:
        raise NotFoundError("Task not found.")
    return task


def _dependency_rows(db: Session, task: Task) -> list[DependencyOut]:
    rows = db.execute(
        select(TaskDependency).where(TaskDependency.task_id == task.id)
    ).scalars().all()
    out = []
    for dep in rows:
        prerequisite = dep.depends_on_task
        out.append(
            DependencyOut(
                id=dep.id,
                depends_on_task_id=dep.depends_on_task_id,
                depends_on_code=prerequisite.code if prerequisite else None,
                depends_on_name=prerequisite.name if prerequisite else None,
                depends_on_status=prerequisite.status if prerequisite else None,
                dependency_type=dep.dependency_type,
                is_blocking=dep.is_blocking,
                is_satisfied=bool(prerequisite and prerequisite.status in _SATISFIED),
            )
        )
    return out


def _detail(db: Session, task: Task) -> TaskDetail:
    dependencies = _dependency_rows(db, task)
    blocked_by = [d for d in dependencies if d.is_blocking and not d.is_satisfied]
    summary = task_summary(task)
    return TaskDetail(
        **summary.model_dump(),
        description=task.description,
        sequence=task.sequence,
        team_lead_id=task.team_lead_id,
        original_estimated_hours=float(task.original_estimated_hours or 0),
        blocked_hours=float(task.blocked_hours or 0),
        submission_count=task.submission_count or 0,
        delay_reason=task.delay_reason,
        delay_note=task.delay_note,
        hold_reason=task.hold_reason,
        hold_note=task.hold_note,
        variance_reason=task.variance_reason,
        variance_note=task.variance_note,
        assigned_at=task.assigned_at,
        started_at=task.started_at,
        submitted_at=task.submitted_at,
        completed_at=task.completed_at,
        created_at=task.created_at,
        updated_at=task.updated_at,
        external_id=task.external_id,
        efficiency_percent=kpi.efficiency(task.estimated_hours, task.actual_hours),
        effort_variance=kpi.effort_variance(task.estimated_hours, task.actual_hours),
        cycle_time_hours=kpi.cycle_time_hours(task.started_at, task.completed_at),
        queue_time_hours=kpi.queue_time_hours(task.assigned_at, task.started_at),
        dependencies=dependencies,
        blocked_by=blocked_by,
        can_start=not blocked_by,
        allowed_transitions=sorted(
            task_service.ALLOWED_TRANSITIONS.get(task.status, set())
        ),
    )


@router.get("", response_model=Page[TaskSummary])
def list_tasks(
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_scope),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    project_id: uuid.UUID | None = None,
    release_id: uuid.UUID | None = None,
    assigned_to_id: uuid.UUID | None = None,
    team_lead_id: uuid.UUID | None = None,
    status: list[str] | None = Query(None),
    priority: list[str] | None = Query(None),
    task_type: str | None = None,
    review_status: str | None = None,
    overdue_only: bool = False,
    open_only: bool = False,
    due_before: date | None = None,
    due_after: date | None = None,
    search: str | None = None,
    sort: str = Query("planned_end"),
) -> Page[TaskSummary]:
    stmt = _visible(scope)

    if project_id:
        stmt = stmt.where(Task.project_id == project_id)
    if release_id:
        stmt = stmt.where(Task.release_id == release_id)
    if assigned_to_id:
        scope.assert_can_view_user(assigned_to_id)
        stmt = stmt.where(Task.assigned_to_id == assigned_to_id)
    if team_lead_id:
        stmt = stmt.where(Task.team_lead_id == team_lead_id)
    if status:
        stmt = stmt.where(Task.status.in_(status))
    if priority:
        stmt = stmt.where(Task.priority.in_(priority))
    if task_type:
        stmt = stmt.where(Task.task_type == task_type)
    if review_status:
        stmt = stmt.where(Task.review_status == review_status)
    if open_only:
        stmt = stmt.where(Task.status.in_(_OPEN_VALUES))
    if overdue_only:
        stmt = stmt.where(
            Task.planned_end < date.today(), Task.status.in_(_OPEN_VALUES)
        )
    if due_before:
        stmt = stmt.where(Task.planned_end <= due_before)
    if due_after:
        stmt = stmt.where(Task.planned_end >= due_after)
    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(or_(Task.name.ilike(pattern), Task.code.ilike(pattern)))

    sort_columns = {
        "planned_end": Task.planned_end,
        "planned_start": Task.planned_start,
        "created_at": Task.created_at,
        "name": Task.name,
        "status": Task.status,
        "priority": Task.priority,
        "sequence": Task.sequence,
        "delay_days": Task.delay_days,
        "estimated_hours": Task.estimated_hours,
    }
    descending = sort.startswith("-")
    column = sort_columns.get(sort.lstrip("-"), Task.planned_end)
    order = column.desc() if descending else column.asc()
    # Nulls last in both directions, so unscheduled tasks never crowd out the
    # ones with real dates at the top of a due-date sort.
    stmt = stmt.order_by(order.nullslast(), Task.sequence.asc())

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar() or 0
    rows = (
        db.execute(stmt.offset((page - 1) * page_size).limit(page_size)).scalars().all()
    )
    return Page.build([task_summary(t) for t in rows], total, page, page_size)


@router.get("/kanban", response_model=KanbanBoard)
def kanban(
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_scope),
    release_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    assigned_to_id: uuid.UUID | None = None,
    limit_per_column: int = Query(100, ge=1, le=300),
) -> KanbanBoard:
    """Board view. Columns are the configured groupings, not raw statuses."""
    stmt = _visible(scope)
    if release_id:
        stmt = stmt.where(Task.release_id == release_id)
    if project_id:
        stmt = stmt.where(Task.project_id == project_id)
    if assigned_to_id:
        scope.assert_can_view_user(assigned_to_id)
        stmt = stmt.where(Task.assigned_to_id == assigned_to_id)

    columns: list[KanbanColumn] = []
    total = 0
    for title, statuses in KANBAN_COLUMNS.items():
        values = [s.value for s in statuses]
        column_stmt = stmt.where(Task.status.in_(values))
        count = (
            db.execute(select(func.count()).select_from(column_stmt.subquery())).scalar()
            or 0
        )
        rows = (
            db.execute(
                column_stmt.order_by(Task.sequence.asc(), Task.planned_end.asc().nullslast())
                .limit(limit_per_column)
            )
            .scalars()
            .all()
        )
        total += count
        columns.append(
            KanbanColumn(
                key=title.lower().replace(" ", "_"),
                title=title,
                statuses=values,
                count=count,
                tasks=[task_summary(t) for t in rows],
            )
        )
    return KanbanBoard(columns=columns, total=total)


@router.get("/my-work", response_model=list[TaskSummary])
def my_work(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    include_completed: bool = False,
) -> list[TaskSummary]:
    """The designer's personal queue, ordered by urgency."""
    stmt = select(Task).where(Task.assigned_to_id == user.id)
    if not include_completed:
        stmt = stmt.where(Task.status.in_(_OPEN_VALUES))
    rows = (
        db.execute(stmt.order_by(Task.planned_end.asc().nullslast(), Task.priority))
        .scalars()
        .all()
    )
    return [task_summary(t) for t in rows]


@router.get("/delay-reasons")
def delay_reasons(
    db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> list[dict]:
    """Configured delay reasons and whether each counts as controllable.

    Open to any authenticated user, like the revision categories: blocking a
    task or submitting a late one requires choosing from this list, so gating
    it behind SETTINGS_VIEW would leave a designer unable to complete a form
    the API insists they fill in. Editing the list is still admin-only.
    """
    return settings_service.get_setting(db, "workflow.delay_reasons")


@router.post("", response_model=TaskDetail, status_code=201)
def create_task(
    payload: TaskCreate,
    request: Request,
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_scope),
    user: User = Depends(require_permission(P.TASK_CREATE)),
) -> TaskDetail:
    # Holding task.create says you may create tasks, not that you may create
    # them anywhere. Unscoped, the permission reached every release in the
    # department -- the same shape create_release had. It answers 404 rather
    # than 403 for a release the caller cannot see, so it cannot be used to
    # discover which releases exist. Anyone with release.view_all is
    # unaffected, everything being visible to them already.
    # Imported here, not at module scope: releases.py already imports
    # task_summary from this module, so a top-level import closes the cycle.
    from app.api.v1.releases import _visible as visible_releases

    release = db.execute(
        visible_releases(scope).where(DesignRelease.id == payload.release_id)
    ).scalar_one_or_none()
    if release is None:
        raise NotFoundError("Design release not found.")

    # Tasks live inside the release window: nothing may begin before the
    # release opens, and work that runs past the end moves the end rather
    # than being silently accepted against a date everyone knows is gone.
    schedule_service.assert_within_window(release, payload.planned_start)

    sequence = payload.sequence
    if sequence is None:
        sequence = (
            db.execute(
                select(func.coalesce(func.max(Task.sequence), 0)).where(
                    Task.release_id == release.id
                )
            ).scalar()
            or 0
        ) + 1

    task = Task(
        code=code_service.next_code(db, "task"),
        project_id=release.project_id,
        release_id=release.id,
        name=payload.name,
        description=payload.description,
        task_type=payload.task_type,
        sequence=sequence,
        team_lead_id=release.team_lead_id,
        required_skill_id=payload.required_skill_id,
        priority=payload.priority,
        complexity=payload.complexity,
        is_mandatory=payload.is_mandatory,
        requires_review=payload.requires_review,
        planned_start=payload.planned_start,
        planned_end=payload.planned_end,
        original_estimated_hours=payload.estimated_hours,
        estimated_hours=payload.estimated_hours,
        status=TaskStatus.NOT_STARTED.value,
        external_id=payload.external_id,
        created_by_id=user.id,
    )
    db.add(task)
    db.flush()

    audit_service.record(
        db,
        entity_type="task",
        entity_id=task.id,
        entity_code=task.code,
        action=AuditAction.CREATE,
        actor=user,
        summary=f"Added task {task.code} to release {release.code}",
        context=client_context(request),
    )

    for dependency_id in payload.depends_on_task_ids:
        task_service.add_dependency(db, task, dependency_id, actor=user)

    if payload.assigned_to_id:
        assignee = db.get(User, payload.assigned_to_id)
        if assignee is None:
            raise NotFoundError("The specified assignee does not exist.")
        task_service.assign(
            db, task, assignee, actor=user, context=client_context(request)
        )

    moved = schedule_service.extend_for_task(
        db, release, task.planned_end, actor=user, context=client_context(request)
    )
    if moved:
        schedule_service.stamp_baseline(release)

    if release is not None:
        schedule_service.extend_for_task(
            db, release, task.planned_end, actor=user, context=client_context(request)
        )

    rollup_service.refresh_chain(db, task)
    return _detail(db, task)


@router.get("/{task_id}", response_model=TaskDetail)
def get_task(
    task_id: uuid.UUID,
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_scope),
) -> TaskDetail:
    return _detail(db, _get_visible(db, scope, task_id))


@router.patch("/{task_id}", response_model=TaskDetail)
def update_task(
    task_id: uuid.UUID,
    payload: TaskUpdate,
    request: Request,
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_scope),
    user: User = Depends(require_permission(P.TASK_UPDATE)),
) -> TaskDetail:
    task = _get_visible(db, scope, task_id)
    tracked = [
        "name", "description", "task_type", "priority", "complexity",
        "is_mandatory", "requires_review", "planned_start", "planned_end",
        "delay_reason", "delay_note", "external_id",
    ]
    before = {f: getattr(task, f) for f in tracked}

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(task, field, value)

    if task.planned_start and task.planned_end and task.planned_end < task.planned_start:
        raise ValidationError("planned_end cannot be before planned_start.")

    db.flush()
    audit_service.record_change(
        db,
        entity_type="task",
        entity_id=task.id,
        entity_code=task.code,
        before=before,
        after={f: getattr(task, f) for f in tracked},
        actor=user,
        context=client_context(request),
    )
    rollup_service.refresh_chain(db, task)
    return _detail(db, task)


@router.post("/{task_id}/assign", response_model=TaskDetail)
def assign_task(
    task_id: uuid.UUID,
    payload: TaskAssign,
    request: Request,
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_scope),
    user: User = Depends(
        require_any_permission(P.TASK_ASSIGN, P.TASK_REASSIGN)
    ),
) -> TaskDetail:
    task = _get_visible(db, scope, task_id)
    assignee = None
    if payload.assigned_to_id is not None:
        assignee = db.get(User, payload.assigned_to_id)
        if assignee is None or not assignee.is_active:
            raise NotFoundError("The specified assignee does not exist or is inactive.")
    task_service.assign(
        db, task, assignee, actor=user, context=client_context(request)
    )
    return _detail(db, task)


@router.post("/{task_id}/estimate", response_model=TaskDetail)
def estimate_task(
    task_id: uuid.UUID,
    payload: TaskEstimate,
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_scope),
    user: User = Depends(require_permission(P.TASK_ESTIMATE)),
) -> TaskDetail:
    task = _get_visible(db, scope, task_id)
    task_service.re_estimate(
        db, task, payload.estimated_hours, reason=payload.reason, actor=user
    )
    rollup_service.refresh_chain(db, task)
    return _detail(db, task)


@router.post("/{task_id}/status", response_model=TaskDetail)
def change_status(
    task_id: uuid.UUID,
    payload: TaskStatusChange,
    request: Request,
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_scope),
    user: User = Depends(
        require_any_permission(P.TASK_EXECUTE, P.TASK_UPDATE)
    ),
) -> TaskDetail:
    task = _get_visible(db, scope, task_id)

    # A designer may only drive their own task. Leads and managers, who hold
    # task.update, may move anything they can see.
    if P.TASK_UPDATE not in user.permission_codes and task.assigned_to_id != user.id:
        raise BusinessRuleError("You can only change the status of your own tasks.")

    task_service.transition(
        db,
        task,
        payload.status,
        actor=user,
        note=payload.note,
        delay_reason=payload.delay_reason,
        hold_reason=payload.hold_reason,
        variance_reason=payload.variance_reason,
        variance_note=payload.variance_note,
        context=client_context(request),
    )
    rollup_service.refresh_chain(db, task)
    return _detail(db, task)


@router.post("/{task_id}/dependencies", response_model=list[DependencyOut], status_code=201)
def add_dependency(
    task_id: uuid.UUID,
    payload: DependencyIn,
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_scope),
    user: User = Depends(require_permission(P.TASK_UPDATE)),
) -> list[DependencyOut]:
    task = _get_visible(db, scope, task_id)
    task_service.add_dependency(
        db,
        task,
        payload.depends_on_task_id,
        is_blocking=payload.is_blocking,
        actor=user,
    )
    return _dependency_rows(db, task)


@router.delete("/{task_id}/dependencies/{dependency_id}", response_model=Message)
def remove_dependency(
    task_id: uuid.UUID,
    dependency_id: uuid.UUID,
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_scope),
    user: User = Depends(require_permission(P.TASK_UPDATE)),
) -> Message:
    task = _get_visible(db, scope, task_id)
    dependency = db.get(TaskDependency, dependency_id)
    if dependency is None or dependency.task_id != task.id:
        raise NotFoundError("Dependency not found on this task.")
    db.delete(dependency)
    db.flush()
    audit_service.record(
        db,
        entity_type="task",
        entity_id=task.id,
        entity_code=task.code,
        action=AuditAction.UPDATE,
        actor=user,
        summary="Removed a dependency",
    )
    return Message(message="Dependency removed.")


@router.get("/{task_id}/deletion-impact")
def task_deletion_impact(
    task_id: uuid.UUID,
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_scope),
    _: User = Depends(require_permission(P.TASK_DELETE)),
) -> dict:
    """What deleting this task would destroy. Read-only."""
    return deletion_service.task_impact(db, _get_visible(db, scope, task_id))


@router.delete("/{task_id}", response_model=Message)
def delete_task(
    task_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_scope),
    user: User = Depends(require_permission(P.TASK_DELETE)),
) -> Message:
    """Permanently delete a task, with its time entries, reviews and revisions.

    A Team Lead keeps this one. A single task is a blast radius somebody
    running the work day to day can be trusted with, and it is the deletion
    people actually need -- a mistyped task is usually added and noticed the
    same afternoon. Cancelling remains available via POST /{id}/status for
    work that was real and then stopped.
    """
    task = _get_visible(db, scope, task_id)
    code = task.code
    impact = deletion_service.delete_task(
        db, task, actor=user, context=client_context(request)
    )
    return Message(
        message=(
            f"Task {code} deleted permanently, with {impact['time_entries']} "
            f"time entries and {impact['logged_hours']}h of logged time."
        )
    )
