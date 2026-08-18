"""Recomputation of derived totals.

Projects and releases store actual hours, rework hours, completion percent and
revision counts. Those columns exist for read speed only -- they are always
recomputed from time entries, tasks and revisions, never written by a user and
never nudged by hand. This module is the only place allowed to set them, so
there is exactly one definition of "the release's actual hours".

Call order is always task -> release -> project, because each level sums the
one below it.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.enums import (
    OPEN_TASK_STATUSES,
    ProjectStatus,
    ReleaseStatus,
    RevisionStatus,
    TaskStatus,
)
from app.models.execution import Revision, TimeEntry
from app.models.project import Project
from app.models.release import DesignRelease
from app.models.task import Task
from app.services import health_service, kpi

_DONE_TASK_VALUES = {TaskStatus.COMPLETED.value, TaskStatus.APPROVED.value}
_OPEN_TASK_VALUES = [s.value for s in OPEN_TASK_STATUSES]


def refresh_task_hours(db: Session, task: Task) -> Task:
    """Recompute a task's actual and rework hours from its time entries."""
    totals = db.execute(
        select(
            func.coalesce(func.sum(TimeEntry.hours), 0),
            func.coalesce(
                func.sum(
                    case((TimeEntry.is_rework.is_(True), TimeEntry.hours), else_=0)
                ),
                0,
            ),
        ).where(TimeEntry.task_id == task.id, TimeEntry.is_running.is_(False))
    ).one()

    task.actual_hours = round(float(totals[0]), 2)
    task.rework_hours = round(float(totals[1]), 2)
    db.flush()
    return task


def refresh_release(db: Session, release: DesignRelease, today: date | None = None) -> DesignRelease:
    """Recompute a release from its tasks."""
    today = today or date.today()
    tasks = db.execute(
        select(Task).where(Task.release_id == release.id)
    ).scalars().all()

    release.actual_hours = round(sum(float(t.actual_hours or 0) for t in tasks), 2)
    release.rework_hours = round(sum(float(t.rework_hours or 0) for t in tasks), 2)
    # Estimated hours are the sum of the current task estimates, so adding or
    # re-estimating a task moves the release plan with it.
    release.estimated_hours = round(sum(float(t.estimated_hours or 0) for t in tasks), 2)
    release.completion_percent = kpi.completion_percent_by_effort(tasks)
    release.revision_count = (
        db.execute(
            select(func.count())
            .select_from(Revision)
            .where(Revision.release_id == release.id)
        ).scalar()
        or 0
    )

    # Derived from the tasks every time rather than stamped once. A one-shot
    # stamp goes stale the moment a task's start is corrected or an earlier
    # task joins the release, which is how a release ended up claiming it
    # started after it finished.
    started = [t.started_at for t in tasks if t.started_at]
    release.actual_start = min(started).date() if started else None

    db.flush()
    return release


def refresh_project(db: Session, project: Project, today: date | None = None) -> Project:
    """Recompute a project from its releases, then re-evaluate health."""
    today = today or date.today()
    releases = db.execute(
        select(DesignRelease).where(DesignRelease.project_id == project.id)
    ).scalars().all()

    project.actual_hours = round(sum(float(r.actual_hours or 0) for r in releases), 2)
    project.rework_hours = round(sum(float(r.rework_hours or 0) for r in releases), 2)
    project.planned_hours = round(
        sum(float(r.estimated_hours or 0) for r in releases), 2
    )
    project.revision_count = sum(int(r.revision_count or 0) for r in releases)

    # Weight each release by its estimated effort so a large release moves the
    # project number more than a small one.
    total_weight = sum(max(float(r.estimated_hours or 0), 0.5) for r in releases)
    if total_weight:
        project.completion_percent = round(
            sum(
                max(float(r.estimated_hours or 0), 0.5)
                * float(r.completion_percent or 0)
                for r in releases
            )
            / total_weight,
            2,
        )
    else:
        project.completion_percent = 0.0

    health_service.refresh_health(db, project, today)
    db.flush()
    return project


def refresh_chain(db: Session, task: Task, today: date | None = None) -> None:
    """Recompute everything affected by a change to one task."""
    today = today or date.today()
    refresh_task_hours(db, task)
    health_service.refresh_task_delay(db, task, today)

    release = db.get(DesignRelease, task.release_id)
    if release is not None:
        refresh_release(db, release, today)
        release.delay_days = kpi.delay_days(
            release.planned_end,
            release.status
            not in {
                ReleaseStatus.COMPLETED.value,
                ReleaseStatus.CANCELLED.value,
                ReleaseStatus.APPROVED.value,
            },
            today,
        )

    project = db.get(Project, task.project_id)
    if project is not None:
        project.delay_days = kpi.delay_days(
            project.required_completion_date,
            project.status
            not in {ProjectStatus.COMPLETED.value, ProjectStatus.CANCELLED.value},
            today,
        )
        refresh_project(db, project, today)


def refresh_revision_hours(db: Session, revision: Revision) -> Revision:
    """Sum the rework logged against one revision."""
    total = (
        db.execute(
            select(func.coalesce(func.sum(TimeEntry.hours), 0)).where(
                TimeEntry.revision_id == revision.id,
                TimeEntry.is_running.is_(False),
            )
        ).scalar()
        or 0
    )
    revision.additional_hours = round(float(total), 2)
    db.flush()
    return revision


def release_completion_blockers(db: Session, release: DesignRelease) -> list[dict]:
    """Mandatory tasks standing between a release and completion.

    An empty list means the release may be completed normally; a non-empty one
    means completion requires the audited manager override (spec section 42).
    """
    rows = db.execute(
        select(Task).where(
            Task.release_id == release.id,
            Task.is_mandatory.is_(True),
            Task.status.in_(_OPEN_TASK_VALUES),
        )
    ).scalars().all()
    return [
        {
            "task_id": str(t.id),
            "code": t.code,
            "name": t.name,
            "status": t.status,
            "assigned_to_id": str(t.assigned_to_id) if t.assigned_to_id else None,
        }
        for t in rows
    ]


def open_revision_for_task(db: Session, task_id: uuid.UUID) -> Revision | None:
    """The revision a task is currently reworking against, if any."""
    return db.execute(
        select(Revision)
        .where(
            Revision.task_id == task_id,
            Revision.status.in_([RevisionStatus.OPEN.value, RevisionStatus.IN_PROGRESS.value]),
        )
        .order_by(Revision.revision_number.desc())
        .limit(1)
    ).scalar_one_or_none()
