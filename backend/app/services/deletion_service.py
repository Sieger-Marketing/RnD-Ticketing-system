"""Permanent deletion of projects, releases and tasks.

Everywhere else in this system "delete" means cancel: the row keeps its
history and drops out of the working view. That is still the right default,
and it is still what a Team Lead gets. This module is the other thing --
actually removing the rows -- and it exists because cancelling does not solve
the problem it was asked to solve. A bulk import that produced the wrong
projects leaves hundreds of rows that are not cancelled work; they are records
of nothing, and they should not sit in the department's history pretending to
be decisions somebody made.

Three rules follow from that, and they are what this module is for:

* **Say what will be destroyed, before destroying it.** Deleting a project
  takes its releases, its tasks and every hour anybody logged against them.
  The caller gets those counts first, so the confirmation can state them and
  nobody discovers the blast radius afterwards.

* **Write the audit entry first.** ``audit_logs.entity_id`` is a plain column
  with no foreign key, precisely so the log outlives the thing it describes.
  Recording before the delete means the one irreversible action in the system
  is also the one that always leaves a trace, including the counts of what
  went with it.

* **Recompute what is left.** Actual hours, completion percent and health are
  stored on projects and releases. Removing rows underneath them without
  recomputing leaves a project reporting hours that no longer exist anywhere,
  which is worse than either the old number or the new one.

Cascades do the structural work: ``Project.releases``, ``DesignRelease.tasks``
and ``Task.time_entries`` are all ``all, delete-orphan``, so ORM deletion of a
parent removes the children. This module counts them, records them, and fixes
up the ancestors the cascade does not reach.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import AuditAction
from app.models.execution import Review, Revision, TimeEntry
from app.models.project import Project
from app.models.release import DesignRelease
from app.models.task import Task
from app.models.user import User
from app.services import audit_service, rollup_service


def _hours_and_entries(db: Session, *, task_ids: list[uuid.UUID]) -> tuple[int, float]:
    """How many time entries sit under these tasks, and how many hours."""
    if not task_ids:
        return 0, 0.0
    count, total = db.execute(
        select(
            func.count(TimeEntry.id),
            func.coalesce(func.sum(TimeEntry.hours), 0),
        ).where(TimeEntry.task_id.in_(task_ids))
    ).one()
    return int(count or 0), round(float(total or 0), 2)


# ---------------------------------------------------------------------------
# What would be destroyed
# ---------------------------------------------------------------------------


def project_impact(db: Session, project: Project) -> dict:
    release_ids = list(
        db.execute(
            select(DesignRelease.id).where(DesignRelease.project_id == project.id)
        ).scalars()
    )
    task_ids = list(
        db.execute(select(Task.id).where(Task.project_id == project.id)).scalars()
    )
    entries, hours = _hours_and_entries(db, task_ids=task_ids)
    return {
        "entity": "project",
        "code": project.code,
        "name": project.name,
        "releases": len(release_ids),
        "tasks": len(task_ids),
        "time_entries": entries,
        "logged_hours": hours,
    }


def release_impact(db: Session, release: DesignRelease) -> dict:
    task_ids = list(
        db.execute(select(Task.id).where(Task.release_id == release.id)).scalars()
    )
    entries, hours = _hours_and_entries(db, task_ids=task_ids)
    return {
        "entity": "release",
        "code": release.code,
        "name": release.name,
        "tasks": len(task_ids),
        "time_entries": entries,
        "logged_hours": hours,
    }


def task_impact(db: Session, task: Task) -> dict:
    entries, hours = _hours_and_entries(db, task_ids=[task.id])
    reviews = (
        db.execute(
            select(func.count()).select_from(Review).where(Review.task_id == task.id)
        ).scalar()
        or 0
    )
    revisions = (
        db.execute(
            select(func.count())
            .select_from(Revision)
            .where(Revision.task_id == task.id)
        ).scalar()
        or 0
    )
    return {
        "entity": "task",
        "code": task.code,
        "name": task.name,
        "time_entries": entries,
        "logged_hours": hours,
        "reviews": int(reviews),
        "revisions": int(revisions),
    }


# ---------------------------------------------------------------------------
# Doing it
# ---------------------------------------------------------------------------


def delete_project(
    db: Session,
    project: Project,
    *,
    actor: User,
    context: dict[str, str | None] | None = None,
) -> dict:
    impact = project_impact(db, project)

    audit_service.record(
        db,
        entity_type="project",
        entity_id=project.id,
        entity_code=project.code,
        action=AuditAction.DELETE,
        actor=actor,
        summary=(
            f"Permanently deleted project {project.code} "
            f"({impact['releases']} releases, {impact['tasks']} tasks, "
            f"{impact['logged_hours']}h logged)"
        ),
        old_value=impact,
        context=context,
    )

    db.delete(project)
    db.flush()
    return impact


def delete_release(
    db: Session,
    release: DesignRelease,
    *,
    actor: User,
    context: dict[str, str | None] | None = None,
) -> dict:
    impact = release_impact(db, release)
    # Held before the delete: afterwards the relationship is gone and there is
    # nothing left to navigate back to the parent with.
    project = release.project

    audit_service.record(
        db,
        entity_type="release",
        entity_id=release.id,
        entity_code=release.code,
        action=AuditAction.DELETE,
        actor=actor,
        summary=(
            f"Permanently deleted release {release.code} "
            f"({impact['tasks']} tasks, {impact['logged_hours']}h logged)"
        ),
        old_value=impact | {"project_id": str(release.project_id)},
        context=context,
    )

    db.delete(release)
    db.flush()

    # The project's hours and completion were partly this release's. Leaving
    # them would have it reporting effort that no longer exists.
    if project is not None:
        rollup_service.refresh_project(db, project, date.today())
    return impact


def delete_task(
    db: Session,
    task: Task,
    *,
    actor: User,
    context: dict[str, str | None] | None = None,
) -> dict:
    impact = task_impact(db, task)
    release = task.release
    project = task.project

    audit_service.record(
        db,
        entity_type="task",
        entity_id=task.id,
        entity_code=task.code,
        action=AuditAction.DELETE,
        actor=actor,
        summary=(
            f"Permanently deleted task {task.code} "
            f"({impact['time_entries']} time entries, {impact['logged_hours']}h logged)"
        ),
        old_value=impact
        | {"release_id": str(task.release_id), "project_id": str(task.project_id)},
        context=context,
    )

    db.delete(task)
    db.flush()

    # refresh_chain starts from the task, which no longer exists, so the two
    # levels above it are refreshed directly instead.
    today = date.today()
    if release is not None:
        rollup_service.refresh_release(db, release, today)
    if project is not None:
        rollup_service.refresh_project(db, project, today)
    return impact
