"""Dashboards and analytics endpoints (spec sections 22-27 and 46)."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import (
    AccessScope,
    get_current_user,
    get_scope,
    require_any_permission,
    require_permission,
)
from app.core.enums import OPEN_TASK_STATUSES, ReleaseStatus, ReviewStatus, TaskStatus
from app.core.errors import NotFoundError
from app.core.permissions import P
from app.db.session import get_db
from app.models.execution import Review
from app.models.project import Project
from app.models.release import DesignRelease
from app.models.task import Task
from app.models.user import Role, User, UserRole
from app.api.v1.tasks import task_summary
from app.services import (
    analytics_service,
    breakdown_service,
    capacity_service,
    health_service,
    kpi,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])

_OPEN_TASKS = [s.value for s in OPEN_TASK_STATUSES]


# ---------------------------------------------------------------------------
# Department / executive
# ---------------------------------------------------------------------------


@router.get("/department")
def department(
    db: Session = Depends(get_db),
    _: User = Depends(
        require_any_permission(
            P.ANALYTICS_VIEW_DEPARTMENT, P.ANALYTICS_VIEW_TEAM
        )
    ),
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict:
    return analytics_service.department_metrics(db, date_from=date_from, date_to=date_to)


@router.get("/breakdown")
def breakdown(
    db: Session = Depends(get_db),
    _: User = Depends(
        require_any_permission(P.ANALYTICS_VIEW_DEPARTMENT, P.ANALYTICS_VIEW_TEAM)
    ),
    dimension: str = Query("product", pattern="^(product|customer|team|project)$"),
    date_from: date | None = None,
    date_to: date | None = None,
    within_dimension: str | None = Query(
        None, pattern="^(product|customer|team|project)$"
    ),
    within_key: uuid.UUID | None = None,
) -> dict:
    """The same figures, cut by product, customer, team or project.

    `within_dimension` and `within_key` together narrow the whole table to one
    group -- the drill-down. Asking for dimension=project within a product
    gives that product's projects described in exactly the columns the products
    themselves were, so the table does not change shape when a reader clicks
    into a row.
    """
    date_to = date_to or date.today()
    date_from = date_from or (date_to - timedelta(days=30))

    within = None
    if within_dimension and within_key:
        within = (within_dimension, within_key)

    return breakdown_service.breakdown(
        db,
        dimension=dimension,
        date_from=date_from,
        date_to=date_to,
        within=within,
    )


@router.get("/trends")
def trends(
    db: Session = Depends(get_db),
    _: User = Depends(
        require_any_permission(P.ANALYTICS_VIEW_DEPARTMENT, P.ANALYTICS_VIEW_TEAM)
    ),
    months: int = Query(6, ge=1, le=24),
) -> list[dict]:
    return analytics_service.monthly_trends(db, months)


@router.get("/bottlenecks")
def bottlenecks(
    db: Session = Depends(get_db),
    _: User = Depends(
        require_any_permission(P.ANALYTICS_VIEW_DEPARTMENT, P.ANALYTICS_VIEW_TEAM)
    ),
    limit: int = Query(10, ge=1, le=50),
) -> dict:
    return analytics_service.bottlenecks(db, limit)


@router.get("/insights")
def insights(
    db: Session = Depends(get_db),
    _: User = Depends(
        require_any_permission(P.ANALYTICS_VIEW_DEPARTMENT, P.ANALYTICS_VIEW_TEAM)
    ),
    limit: int = Query(12, ge=1, le=50),
) -> list[dict]:
    """Exceptions and wins the management insight engine found in the data."""
    return analytics_service.insights(db, limit)


@router.get("/dashboard/executive")
def executive_dashboard(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(P.ANALYTICS_VIEW_DEPARTMENT)),
    months: int = Query(6, ge=1, le=24),
) -> dict:
    """The Director's view: KPIs, trends and exceptions, not task-level noise."""
    metrics = analytics_service.department_metrics(db)

    pipeline = [
        {"status": status, "count": count}
        for status, count in db.execute(
            select(Project.status, func.count()).group_by(Project.status)
        ).all()
    ]

    delayed_projects = [
        {
            "id": str(p.id),
            "code": p.code,
            "name": p.name,
            "customer": p.customer.name if p.customer else None,
            "health": p.health,
            "delay_days": p.delay_days,
            "completion_percent": float(p.completion_percent or 0),
            "reasons": p.health_reasons or [],
        }
        for p in db.execute(
            select(Project)
            .where(Project.delay_days > 0)
            .order_by(Project.delay_days.desc())
            .limit(10)
        ).scalars()
    ]

    leads = (
        db.execute(
            select(User)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .where(Role.name == "Team Lead", User.is_active.is_(True))
        )
        .scalars()
        .all()
    )
    designers = (
        db.execute(
            select(User)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .where(Role.name == "Designer", User.is_active.is_(True))
        )
        .scalars()
        .all()
    )

    today = date.today()
    horizon = today + timedelta(days=14)

    return {
        "kpis": metrics,
        "project_pipeline": pipeline,
        "capacity_vs_demand": analytics_service.department_utilization(
            db, today, horizon
        ),
        "monthly_output": analytics_service.monthly_trends(db, months),
        "team_lead_performance": [
            {
                "id": str(lead.id),
                "full_name": lead.full_name,
                **{
                    k: v
                    for k, v in analytics_service.team_lead_metrics(db, lead).items()
                    if k
                    in {
                        "releases_assigned",
                        "releases_completed",
                        "releases_delayed",
                        "team_efficiency_percent",
                        "team_utilization_percent",
                        "team_on_time_percent",
                        "rework_percent",
                        "first_pass_approval_percent",
                        "average_review_turnaround_hours",
                    }
                },
            }
            for lead in leads
        ],
        "designer_performance": [
            {
                "id": str(designer.id),
                "full_name": designer.full_name,
                **{
                    k: v
                    for k, v in analytics_service.designer_metrics(db, designer).items()
                    if k
                    in {
                        "tasks_completed",
                        "efficiency_percent",
                        "utilization_percent",
                        "utilization_band",
                        "on_time_percent",
                        "rework_percent",
                        "first_pass_approval_percent",
                        "performance_score",
                    }
                },
            }
            for designer in designers
        ],
        "bottlenecks": analytics_service.bottlenecks(db, 5),
        "delayed_projects": delayed_projects,
        "insights": analytics_service.insights(db),
    }


# ---------------------------------------------------------------------------
# Design manager
# ---------------------------------------------------------------------------


@router.get("/dashboard/manager")
def manager_dashboard(
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_scope),
    _: User = Depends(require_permission(P.PROJECT_VIEW_ALL)),
) -> dict:
    """The operational command centre."""
    today = date.today()
    week_end = today + timedelta(days=7)

    due_today = (
        db.execute(
            select(Task)
            .where(Task.planned_end == today, Task.status.in_(_OPEN_TASKS))
            .order_by(Task.priority)
        )
        .scalars()
        .all()
    )
    due_this_week = (
        db.execute(
            select(Task)
            .where(
                Task.planned_end.between(today, week_end),
                Task.status.in_(_OPEN_TASKS),
            )
            .order_by(Task.planned_end)
        )
        .scalars()
        .all()
    )
    overdue = (
        db.execute(
            select(Task)
            .where(Task.planned_end < today, Task.status.in_(_OPEN_TASKS))
            .order_by(Task.delay_days.desc())
            .limit(50)
        )
        .scalars()
        .all()
    )
    blocked = (
        db.execute(select(Task).where(Task.status == TaskStatus.BLOCKED.value))
        .scalars()
        .all()
    )

    release_progress = [
        {
            "id": str(r.id),
            "code": r.code,
            "name": r.name,
            "project_code": r.project.code if r.project else None,
            "status": r.status,
            "health": r.health,
            "completion_percent": float(r.completion_percent or 0),
            "estimated_hours": float(r.estimated_hours or 0),
            "actual_hours": float(r.actual_hours or 0),
            "effort_variance": kpi.effort_variance(r.estimated_hours, r.actual_hours),
            "efficiency_percent": kpi.efficiency(r.estimated_hours, r.actual_hours),
            "delay_days": r.delay_days or 0,
            "team_lead": r.team_lead.full_name if r.team_lead else None,
        }
        for r in db.execute(
            select(DesignRelease)
            .where(
                DesignRelease.status.notin_(
                    [ReleaseStatus.COMPLETED.value, ReleaseStatus.CANCELLED.value]
                )
            )
            .order_by(DesignRelease.planned_end.asc().nullslast())
            .limit(50)
        ).scalars()
    ]

    designers = analytics_service.execution_staff(db)
    heatmap = capacity_service.team_capacity(
        db, [u.id for u in designers], today, today + timedelta(days=13)
    )

    return {
        "kpis": analytics_service.department_metrics(db),
        "todays_workload": [task_summary(t).model_dump(mode="json") for t in due_today],
        "due_this_week": [
            task_summary(t).model_dump(mode="json") for t in due_this_week
        ],
        "overdue_tasks": [
            {
                **task_summary(t).model_dump(mode="json"),
                "delay_reason": t.delay_reason,
                "team_lead": t.team_lead.full_name if t.team_lead else None,
            }
            for t in overdue
        ],
        "blocked_tasks": [task_summary(t).model_dump(mode="json") for t in blocked],
        "pending_reviews": [
            {
                "id": str(r.id),
                "code": r.code,
                "task_code": r.task.code if r.task else None,
                "task_name": r.task.name if r.task else None,
                "reviewer": r.reviewer.full_name if r.reviewer else None,
                "submitted_at": r.submitted_at.isoformat(),
                "round_number": r.round_number,
            }
            for r in db.execute(
                select(Review)
                .where(
                    Review.status.in_(
                        [ReviewStatus.PENDING.value, ReviewStatus.IN_REVIEW.value]
                    )
                )
                .order_by(Review.submitted_at)
            ).scalars()
        ],
        "capacity_heatmap": heatmap,
        "release_progress": release_progress,
        "insights": analytics_service.insights(db),
    }


# ---------------------------------------------------------------------------
# Team lead
# ---------------------------------------------------------------------------


@router.get("/dashboard/team-lead")
def team_lead_dashboard(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    lead_id: uuid.UUID | None = None,
) -> dict:
    """A Team Lead's own view; managers may pass `lead_id` to inspect one."""
    lead = user
    if lead_id and lead_id != user.id:
        if P.ANALYTICS_VIEW_DEPARTMENT not in user.permission_codes:
            raise NotFoundError("Team Lead not found.")
        lead = db.get(User, lead_id)
        if lead is None:
            raise NotFoundError("Team Lead not found.")

    today = date.today()
    metrics = analytics_service.team_lead_metrics(db, lead)

    releases = (
        db.execute(
            select(DesignRelease)
            .where(DesignRelease.team_lead_id == lead.id)
            .order_by(DesignRelease.planned_end.asc().nullslast())
        )
        .scalars()
        .all()
    )
    member_ids = [u.id for u in lead.direct_reports if u.is_active] or [lead.id]

    return {
        "kpis": metrics,
        "my_releases": [
            {
                "id": str(r.id),
                "code": r.code,
                "name": r.name,
                "project_code": r.project.code if r.project else None,
                "status": r.status,
                "health": r.health,
                "completion_percent": float(r.completion_percent or 0),
                "delay_days": r.delay_days or 0,
                "planned_end": r.planned_end.isoformat() if r.planned_end else None,
                "health_reasons": r.health_reasons or [],
            }
            for r in releases
        ],
        "team": metrics["team_capacity"],
        "tasks_due_today": [
            task_summary(t).model_dump(mode="json")
            for t in db.execute(
                select(Task).where(
                    Task.assigned_to_id.in_(member_ids),
                    Task.planned_end == today,
                    Task.status.in_(_OPEN_TASKS),
                )
            ).scalars()
        ],
        "overdue_tasks": [
            task_summary(t).model_dump(mode="json")
            for t in db.execute(
                select(Task)
                .where(
                    Task.assigned_to_id.in_(member_ids),
                    Task.planned_end < today,
                    Task.status.in_(_OPEN_TASKS),
                )
                .order_by(Task.delay_days.desc())
            ).scalars()
        ],
        "blocked_tasks": [
            task_summary(t).model_dump(mode="json")
            for t in db.execute(
                select(Task).where(
                    Task.team_lead_id == lead.id,
                    Task.status == TaskStatus.BLOCKED.value,
                )
            ).scalars()
        ],
        "review_queue": [
            {
                "id": str(r.id),
                "code": r.code,
                "task_code": r.task.code if r.task else None,
                "task_name": r.task.name if r.task else None,
                "submitted_at": r.submitted_at.isoformat(),
                "round_number": r.round_number,
                "submitted_by": r.submitted_by.full_name if r.submitted_by else None,
            }
            for r in db.execute(
                select(Review)
                .where(
                    Review.reviewer_id == lead.id,
                    Review.status.in_(
                        [ReviewStatus.PENDING.value, ReviewStatus.IN_REVIEW.value]
                    ),
                )
                .order_by(Review.submitted_at)
            ).scalars()
        ],
    }


# ---------------------------------------------------------------------------
# Designer
# ---------------------------------------------------------------------------


@router.get("/dashboard/designer")
def designer_dashboard(
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_scope),
    user_id: uuid.UUID | None = None,
) -> dict:
    """Personal workspace."""
    target = scope.user
    if user_id and user_id != scope.user.id:
        scope.assert_can_view_user(user_id)
        target = db.get(User, user_id)
        if target is None:
            raise NotFoundError("User not found.")

    today = date.today()
    week_end = today + timedelta(days=7)

    def _tasks(*filters):
        return [
            task_summary(t).model_dump(mode="json")
            for t in db.execute(
                select(Task)
                .where(Task.assigned_to_id == target.id, *filters)
                .order_by(Task.planned_end.asc().nullslast())
            ).scalars()
        ]

    return {
        "kpis": analytics_service.designer_metrics(db, target),
        "todays_tasks": _tasks(Task.planned_end == today, Task.status.in_(_OPEN_TASKS)),
        "upcoming_tasks": _tasks(
            Task.planned_end.between(today + timedelta(days=1), week_end),
            Task.status.in_(_OPEN_TASKS),
        ),
        "overdue_tasks": _tasks(
            Task.planned_end < today, Task.status.in_(_OPEN_TASKS)
        ),
        "in_review": _tasks(
            Task.status.in_(
                [
                    TaskStatus.SUBMITTED_FOR_REVIEW.value,
                    TaskStatus.UNDER_REVIEW.value,
                ]
            )
        ),
        "revision_required": _tasks(
            Task.status == TaskStatus.REVISION_REQUIRED.value
        ),
        "recently_completed": _tasks(
            Task.status.in_([TaskStatus.COMPLETED.value, TaskStatus.APPROVED.value]),
            Task.completed_at.is_not(None),
        )[:10],
    }


# ---------------------------------------------------------------------------
# Per-entity analytics
# ---------------------------------------------------------------------------


@router.get("/projects/{project_id}")
def project_dashboard(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_scope),
) -> dict:
    """A single project's dashboard (spec section 26)."""
    project = db.get(Project, project_id)
    if project is None:
        raise NotFoundError("Project not found.")

    releases = (
        db.execute(
            select(DesignRelease)
            .where(DesignRelease.project_id == project.id)
            .order_by(DesignRelease.sequence_number)
        )
        .scalars()
        .all()
    )
    tasks = (
        db.execute(select(Task).where(Task.project_id == project.id)).scalars().all()
    )
    today = date.today()

    completed_tasks = [t for t in tasks if t.status in {"Completed", "Approved"}]
    on_time = sum(
        1
        for t in completed_tasks
        if t.planned_end and t.completed_at and t.completed_at.date() <= t.planned_end
    )
    dated = sum(1 for t in completed_tasks if t.planned_end)

    contributors: dict[str, dict] = {}
    for task in tasks:
        if task.assigned_to_id is None:
            continue
        key = str(task.assigned_to_id)
        row = contributors.setdefault(
            key,
            {
                "user_id": key,
                "full_name": task.assigned_to.full_name if task.assigned_to else None,
                "tasks": 0,
                "estimated_hours": 0.0,
                "actual_hours": 0.0,
            },
        )
        row["tasks"] += 1
        row["estimated_hours"] += float(task.estimated_hours or 0)
        row["actual_hours"] += float(task.actual_hours or 0)

    return {
        "project": {
            "id": str(project.id),
            "code": project.code,
            "name": project.name,
            "status": project.status,
            "health": project.health,
            "health_reasons": project.health_reasons or [],
            "completion_percent": float(project.completion_percent or 0),
            "planned_hours": float(project.planned_hours or 0),
            "actual_hours": float(project.actual_hours or 0),
            "rework_hours": float(project.rework_hours or 0),
            "revision_count": project.revision_count or 0,
            "delay_days": project.delay_days or 0,
            "efficiency_percent": kpi.efficiency(
                project.planned_hours, project.actual_hours
            ),
            "rework_percent": kpi.rework_percent(
                project.rework_hours, project.actual_hours
            ),
            "on_time_percent": kpi.on_time_percent(on_time, dated),
        },
        "release_counts": {
            "total": len(releases),
            "completed": sum(
                1 for r in releases if r.status == ReleaseStatus.COMPLETED.value
            ),
            "in_progress": sum(
                1
                for r in releases
                if r.status
                not in {ReleaseStatus.COMPLETED.value, ReleaseStatus.CANCELLED.value}
            ),
            "overdue": sum(1 for r in releases if (r.delay_days or 0) > 0),
        },
        "task_counts": {
            "total": len(tasks),
            "completed": len(completed_tasks),
            "open": sum(1 for t in tasks if t.status in _OPEN_TASKS),
            "overdue": sum(
                1
                for t in tasks
                if t.planned_end and t.planned_end < today and t.status in _OPEN_TASKS
            ),
            "blocked": sum(1 for t in tasks if t.status == TaskStatus.BLOCKED.value),
        },
        "timeline": [
            {
                "id": str(r.id),
                "code": r.code,
                "name": r.name,
                "sequence": r.sequence_number,
                "status": r.status,
                "health": r.health,
                "completion_percent": float(r.completion_percent or 0),
                "planned_start": r.planned_start.isoformat() if r.planned_start else None,
                "planned_end": r.planned_end.isoformat() if r.planned_end else None,
                "actual_start": r.actual_start.isoformat() if r.actual_start else None,
                "actual_end": r.actual_end.isoformat() if r.actual_end else None,
                "estimated_hours": float(r.estimated_hours or 0),
                "actual_hours": float(r.actual_hours or 0),
                "delay_days": r.delay_days or 0,
            }
            for r in releases
        ],
        "resource_allocation": sorted(
            contributors.values(), key=lambda c: -c["actual_hours"]
        ),
    }


@router.get("/users/{user_id}")
def user_performance(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_scope),
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict:
    scope.assert_can_view_user(user_id)
    target = db.get(User, user_id)
    if target is None:
        raise NotFoundError("User not found.")
    return analytics_service.designer_metrics(
        db, target, date_from=date_from, date_to=date_to
    )


@router.post("/refresh-delays")
def refresh_delays(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(P.SETTINGS_MANAGE)),
) -> dict:
    """Recompute delay days across the department."""
    return health_service.sweep_delays(db)
