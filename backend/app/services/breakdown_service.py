"""The same performance question, asked along different lines.

"How are we doing" is not one question. A design manager asks it per product,
because a Tower behaves nothing like a Stacker. A director asks it per
customer, because that is how the commercial conversation is framed. A team
lead asks it per team. The arithmetic is identical in all three cases; only the
line the rows are cut along changes.

So there is one implementation and three groupings, and every row carries the
same fields. That is what lets the screen be a single table with a switch above
it rather than three screens that drift apart, and it is what lets a row be
drilled into: the projects behind a product are described with the same
columns as the product itself.

Everything is derived. Nothing here can be typed in or overridden.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable

from sqlalchemy import Select, case, func, select
from sqlalchemy.orm import Session

from app.core.enums import OPEN_TASK_STATUSES, ProjectStatus, ReleaseStatus, ReviewResult, TaskStatus
from app.models.catalog import Customer, Product
from app.models.execution import Review, Revision
from app.models.project import Project
from app.models.release import DesignRelease
from app.models.task import Task
from app.models.user import User
from app.services import kpi

_OPEN_TASKS = [s.value for s in OPEN_TASK_STATUSES]
_DONE_TASKS = [TaskStatus.COMPLETED.value, TaskStatus.APPROVED.value]
_ACTIVE_PROJECTS = [
    s.value
    for s in ProjectStatus
    if s not in {ProjectStatus.COMPLETED, ProjectStatus.CANCELLED}
]
_ACTIVE_RELEASES = [
    s.value
    for s in ReleaseStatus
    if s not in {ReleaseStatus.COMPLETED, ReleaseStatus.CANCELLED}
]

#: Rows whose grouping value is null -- a project with no product yet, a task
#: with no team lead. They are shown rather than dropped, because work nobody
#: has classified is exactly the work that goes unnoticed.
UNASSIGNED = "Unassigned"


@dataclass(frozen=True, slots=True)
class Dimension:
    """One way of cutting the same numbers."""

    key: str
    label: str
    #: Plural noun for the column header, e.g. "Product".
    row_label: str
    #: Applied to a Task-rooted select to reach the grouping column.
    join: Callable[[Select], Select]
    #: The column rows are grouped by.
    column: Any
    #: id -> display name, for every value the grouping can produce.
    names: Callable[[Session], dict[uuid.UUID, str]]


def _names(db: Session, model) -> dict[uuid.UUID, str]:
    return {row.id: row.name for row in db.execute(select(model)).scalars()}


def _people(db: Session) -> dict[uuid.UUID, str]:
    return {row.id: row.full_name for row in db.execute(select(User)).scalars()}


DIMENSIONS: dict[str, Dimension] = {
    "product": Dimension(
        key="product",
        label="By product",
        row_label="Product",
        join=lambda stmt: stmt.join(Project, Project.id == Task.project_id),
        column=Project.product_id,
        names=lambda db: _names(db, Product),
    ),
    "customer": Dimension(
        key="customer",
        label="By customer",
        row_label="Customer",
        join=lambda stmt: stmt.join(Project, Project.id == Task.project_id),
        column=Project.customer_id,
        names=lambda db: _names(db, Customer),
    ),
    "team": Dimension(
        key="team",
        label="By team",
        row_label="Team lead",
        join=lambda stmt: stmt,
        column=Task.team_lead_id,
        names=_people,
    ),
    # The drill-down target. Same columns, one level down, so the table the
    # reader is looking at does not change shape when they click into it.
    "project": Dimension(
        key="project",
        label="By project",
        row_label="Project",
        join=lambda stmt: stmt,
        column=Task.project_id,
        names=lambda db: {
            row.id: f"{row.code} {row.name}"
            for row in db.execute(select(Project)).scalars()
        },
    ),
}


def _blank_row() -> dict:
    return {
        "tasks_completed": 0,
        "tasks_open": 0,
        "tasks_overdue": 0,
        "planned_hours": 0.0,
        "actual_hours": 0.0,
        "rework_hours": 0.0,
        "on_time": 0,
        "on_time_denominator": 0,
        "projects": 0,
        "releases": 0,
        "revisions": 0,
        "reviews_submitted": 0,
        "reviews_first_pass": 0,
        "cycle_hours": [],
        "health": {"RED": 0, "AMBER": 0, "GREEN": 0},
    }


def _bucket(rows: dict, key) -> dict:
    return rows.setdefault(key, _blank_row())


def _completed_in_period(
    db: Session, dim: Dimension, date_from: date, date_to: date, scope
) -> dict:
    """Hours, counts and on-time, for work finished inside the window."""
    stmt = dim.join(
        select(
            dim.column,
            func.count(),
            func.coalesce(func.sum(Task.estimated_hours), 0),
            func.coalesce(func.sum(Task.actual_hours), 0),
            func.coalesce(func.sum(Task.rework_hours), 0),
        )
        .select_from(Task)
        .where(
            Task.status.in_(_DONE_TASKS),
            Task.completed_at.is_not(None),
            func.date(Task.completed_at).between(date_from, date_to),
            *scope,
        )
        .group_by(dim.column)
    )

    out: dict = {}
    for key, count, estimated, actual, rework in db.execute(stmt).all():
        row = _bucket(out, key)
        row["tasks_completed"] = int(count or 0)
        row["planned_hours"] = float(estimated or 0)
        row["actual_hours"] = float(actual or 0)
        row["rework_hours"] = float(rework or 0)
    return out


def _on_time(db: Session, dim: Dimension, date_from: date, date_to: date, scope) -> dict:
    """On-time counts. Tasks with no planned end are in neither number."""
    stmt = dim.join(
        select(
            dim.column,
            func.count(),
            func.coalesce(
                func.sum(
                    case((func.date(Task.completed_at) <= Task.planned_end, 1), else_=0)
                ),
                0,
            ),
        )
        .select_from(Task)
        .where(
            Task.status.in_(_DONE_TASKS),
            Task.completed_at.is_not(None),
            Task.planned_end.is_not(None),
            func.date(Task.completed_at).between(date_from, date_to),
            *scope,
        )
        .group_by(dim.column)
    )
    return {
        key: {"denominator": int(total or 0), "on_time": int(punctual or 0)}
        for key, total, punctual in db.execute(stmt).all()
    }


def _open_and_overdue(db: Session, dim: Dimension, today: date, scope) -> dict:
    """A snapshot, not a period figure: what is outstanding right now."""
    stmt = dim.join(
        select(
            dim.column,
            func.count(),
            func.coalesce(
                func.sum(
                    case(
                        (
                            (Task.planned_end.is_not(None))
                            & (Task.planned_end < today),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
        )
        .select_from(Task)
        .where(Task.status.in_(_OPEN_TASKS), *scope)
        .group_by(dim.column)
    )
    return {
        key: {"open": int(total or 0), "overdue": int(overdue or 0)}
        for key, total, overdue in db.execute(stmt).all()
    }


def _distinct_counts(db: Session, dim: Dimension, scope) -> dict:
    stmt = dim.join(
        select(
            dim.column,
            func.count(func.distinct(Task.project_id)),
            func.count(func.distinct(Task.release_id)),
        )
        .select_from(Task)
        .where(*scope)
        .group_by(dim.column)
    )
    return {
        key: {"projects": int(projects or 0), "releases": int(releases or 0)}
        for key, projects, releases in db.execute(stmt).all()
    }


def _revisions(db: Session, dim: Dimension, date_from: date, date_to: date, scope) -> dict:
    """Rework raised inside the window, counted on the same basis as the tasks.

    Joined through Task so every dimension reaches it the same way, and so the
    period on the numerator matches the period on the denominator -- comparing
    all-time rework against one month's completions is how a revision rate ends
    up reading in the hundreds.
    """
    stmt = dim.join(
        select(dim.column, func.count())
        .select_from(Revision)
        .join(Task, Task.id == Revision.task_id)
        .where(
            func.date(Revision.created_at).between(date_from, date_to),
            *scope,
        )
        .group_by(dim.column)
    )
    return {key: int(count or 0) for key, count in db.execute(stmt).all()}


def _first_pass(db: Session, dim: Dimension, date_from: date, date_to: date, scope) -> dict:
    """Approved on the first review, over everything submitted for review."""
    stmt = dim.join(
        select(
            dim.column,
            func.count(func.distinct(Review.task_id)),
            func.count(
                func.distinct(
                    case(
                        (
                            (Review.round_number == 1)
                            & (Review.result == ReviewResult.APPROVED.value),
                            Review.task_id,
                        ),
                        else_=None,
                    )
                )
            ),
        )
        .select_from(Review)
        .join(Task, Task.id == Review.task_id)
        .where(
            func.date(Review.created_at).between(date_from, date_to),
            *scope,
        )
        .group_by(dim.column)
    )
    return {
        key: {"submitted": int(submitted or 0), "first_pass": int(first or 0)}
        for key, submitted, first in db.execute(stmt).all()
    }


def _cycle_times(db: Session, dim: Dimension, date_from: date, date_to: date, scope) -> dict:
    stmt = dim.join(
        select(dim.column, Task.started_at, Task.completed_at)
        .select_from(Task)
        .where(
            Task.status.in_(_DONE_TASKS),
            Task.started_at.is_not(None),
            Task.completed_at.is_not(None),
            func.date(Task.completed_at).between(date_from, date_to),
            *scope,
        )
    )
    out: dict = {}
    for key, started, completed in db.execute(stmt).all():
        hours = kpi.cycle_time_hours(started, completed)
        if hours is not None:
            out.setdefault(key, []).append(hours)
    return out


def _health_scope(within: tuple[str, uuid.UUID] | None, *, release_rooted: bool) -> list:
    """The drill-down filter, restated for a query that is not rooted on Task.

    The other queries reach the grouping column through Task and share one set
    of filters. These two do not -- health is a property of a project or a
    release, not of a task -- so the same narrowing has to be expressed against
    whichever table this query starts from. Omitting it was a real bug: every
    active project got a bucket regardless of the drill-down, so opening one
    product listed every project in the department.
    """
    if within is None:
        return []

    parent, value = within

    if release_rooted:
        if parent == "product":
            return [DesignRelease.product_id == value]
        if parent == "customer":
            return [
                DesignRelease.project_id.in_(
                    select(Project.id).where(Project.customer_id == value)
                )
            ]
        if parent == "team":
            return [DesignRelease.team_lead_id == value]
        if parent == "project":
            return [DesignRelease.project_id == value]
        return []

    if parent == "product":
        return [Project.product_id == value]
    if parent == "customer":
        return [Project.customer_id == value]
    if parent == "project":
        return [Project.id == value]
    if parent == "team":
        return [
            Project.id.in_(
                select(DesignRelease.project_id).where(
                    DesignRelease.team_lead_id == value
                )
            )
        ]
    return []


def _health(
    db: Session, dim: Dimension, within: tuple[str, uuid.UUID] | None
) -> dict:
    """RAG counts for the live work in each group.

    Products and customers are counted in projects, because that is the unit a
    manager acts on. A team is counted in releases, because a team lead holds
    releases rather than projects.
    """
    out: dict = {}
    release_rooted = dim.key == "team"
    narrowing = _health_scope(within, release_rooted=release_rooted)

    if release_rooted:
        stmt = (
            select(DesignRelease.team_lead_id, DesignRelease.health, func.count())
            .where(DesignRelease.status.in_(_ACTIVE_RELEASES), *narrowing)
            .group_by(DesignRelease.team_lead_id, DesignRelease.health)
        )
    elif dim.key == "project":
        stmt = (
            select(Project.id, Project.health, func.count())
            .where(Project.status.in_(_ACTIVE_PROJECTS), *narrowing)
            .group_by(Project.id, Project.health)
        )
    else:
        column = Project.product_id if dim.key == "product" else Project.customer_id
        stmt = (
            select(column, Project.health, func.count())
            .where(Project.status.in_(_ACTIVE_PROJECTS), *narrowing)
            .group_by(column, Project.health)
        )

    for key, health, count in db.execute(stmt).all():
        bucket = out.setdefault(key, {"RED": 0, "AMBER": 0, "GREEN": 0})
        if health in bucket:
            bucket[health] += int(count or 0)
    return out


def _scope_for(dimension: str, value: uuid.UUID | None) -> list:
    """Restrict every query to one group, for a drill-down."""
    if value is None:
        return []
    if dimension == "product":
        return [Project.product_id == value]
    if dimension == "customer":
        return [Project.customer_id == value]
    if dimension == "team":
        return [Task.team_lead_id == value]
    if dimension == "project":
        return [Task.project_id == value]
    return []


def breakdown(
    db: Session,
    *,
    dimension: str,
    date_from: date,
    date_to: date,
    within: tuple[str, uuid.UUID] | None = None,
    today: date | None = None,
) -> dict:
    """Performance by product, customer, team or project.

    `within` narrows every row to one group from another dimension -- the
    drill-down: projects *within* a product, cut the same way as the products
    were.
    """
    if dimension not in DIMENSIONS:
        raise KeyError(dimension)

    dim = DIMENSIONS[dimension]
    today = today or date.today()

    scope: list = []
    if within is not None:
        parent_dimension, parent_value = within
        scope = _scope_for(parent_dimension, parent_value)
        # Reaching a project column from a task needs the join the parent
        # dimension would have added.
        if parent_dimension in {"product", "customer"} and dim.key == "team":
            dim = Dimension(
                key=dim.key,
                label=dim.label,
                row_label=dim.row_label,
                join=lambda stmt: stmt.join(Project, Project.id == Task.project_id),
                column=dim.column,
                names=dim.names,
            )
        if parent_dimension in {"product", "customer"} and dim.key == "project":
            dim = Dimension(
                key=dim.key,
                label=dim.label,
                row_label=dim.row_label,
                join=lambda stmt: stmt.join(Project, Project.id == Task.project_id),
                column=dim.column,
                names=dim.names,
            )

    rows: dict = {}
    for key, values in _completed_in_period(db, dim, date_from, date_to, scope).items():
        _bucket(rows, key).update(values)

    for key, values in _on_time(db, dim, date_from, date_to, scope).items():
        row = _bucket(rows, key)
        row["on_time"] = values["on_time"]
        row["on_time_denominator"] = values["denominator"]

    for key, values in _open_and_overdue(db, dim, today, scope).items():
        row = _bucket(rows, key)
        row["tasks_open"] = values["open"]
        row["tasks_overdue"] = values["overdue"]

    for key, values in _distinct_counts(db, dim, scope).items():
        row = _bucket(rows, key)
        row["projects"] = values["projects"]
        row["releases"] = values["releases"]

    for key, count in _revisions(db, dim, date_from, date_to, scope).items():
        _bucket(rows, key)["revisions"] = count

    for key, values in _first_pass(db, dim, date_from, date_to, scope).items():
        row = _bucket(rows, key)
        row["reviews_submitted"] = values["submitted"]
        row["reviews_first_pass"] = values["first_pass"]

    for key, hours in _cycle_times(db, dim, date_from, date_to, scope).items():
        _bucket(rows, key)["cycle_hours"] = hours

    health = _health(db, dim, within)
    for key, values in health.items():
        # Health is a snapshot of live work, so a group can have health without
        # having completed anything in the window.
        _bucket(rows, key)["health"] = values

    names = dim.names(db)

    out = []
    for key, row in rows.items():
        out.append(
            {
                "key": str(key) if key else None,
                "label": names.get(key, UNASSIGNED) if key else UNASSIGNED,
                "projects": row["projects"],
                "releases": row["releases"],
                "tasks_completed": row["tasks_completed"],
                "tasks_open": row["tasks_open"],
                "tasks_overdue": row["tasks_overdue"],
                "planned_hours": round(row["planned_hours"], 2),
                "actual_hours": round(row["actual_hours"], 2),
                "rework_hours": round(row["rework_hours"], 2),
                "efficiency_percent": kpi.efficiency(
                    row["planned_hours"], row["actual_hours"]
                ),
                "effort_variance_hours": kpi.effort_variance(
                    row["planned_hours"], row["actual_hours"]
                ),
                "on_time_percent": kpi.on_time_percent(
                    row["on_time"], row["on_time_denominator"]
                ),
                "rework_percent": kpi.rework_percent(
                    row["rework_hours"], row["actual_hours"]
                ),
                "first_pass_approval_percent": kpi.first_pass_approval_percent(
                    row["reviews_first_pass"], row["reviews_submitted"]
                ),
                "revision_rate_percent": kpi.revision_rate(
                    row["revisions"], row["tasks_completed"]
                ),
                "average_cycle_time_hours": kpi.average(row["cycle_hours"]),
                "health": row["health"],
            }
        )

    # Busiest first: the rows carrying the most delivered work are the ones a
    # reader should weigh most, and an alphabetical list buries them.
    out.sort(key=lambda r: (-r["actual_hours"], r["label"]))

    totals = _totals(rows)

    return {
        "dimension": dim.key,
        "row_label": dim.row_label,
        "period": {"from": date_from.isoformat(), "to": date_to.isoformat()},
        "within": (
            {"dimension": within[0], "key": str(within[1])} if within else None
        ),
        "rows": out,
        "totals": totals,
    }


def _totals(rows: dict) -> dict:
    """The department figure, computed from the same rows the table shows.

    Deliberately not the sum of the per-row percentages: an average of
    percentages weights a product with four hours the same as one with four
    hundred. These are recomputed from the underlying totals.
    """
    planned = sum(r["planned_hours"] for r in rows.values())
    actual = sum(r["actual_hours"] for r in rows.values())
    rework = sum(r["rework_hours"] for r in rows.values())
    completed = sum(r["tasks_completed"] for r in rows.values())
    on_time = sum(r["on_time"] for r in rows.values())
    on_time_denominator = sum(r["on_time_denominator"] for r in rows.values())
    revisions = sum(r["revisions"] for r in rows.values())
    submitted = sum(r["reviews_submitted"] for r in rows.values())
    first_pass = sum(r["reviews_first_pass"] for r in rows.values())
    cycle = [h for r in rows.values() for h in r["cycle_hours"]]

    return {
        "tasks_completed": completed,
        "tasks_open": sum(r["tasks_open"] for r in rows.values()),
        "tasks_overdue": sum(r["tasks_overdue"] for r in rows.values()),
        "planned_hours": round(planned, 2),
        "actual_hours": round(actual, 2),
        "rework_hours": round(rework, 2),
        "efficiency_percent": kpi.efficiency(planned, actual),
        "effort_variance_hours": kpi.effort_variance(planned, actual),
        "on_time_percent": kpi.on_time_percent(on_time, on_time_denominator),
        "rework_percent": kpi.rework_percent(rework, actual),
        "first_pass_approval_percent": kpi.first_pass_approval_percent(
            first_pass, submitted
        ),
        "revision_rate_percent": kpi.revision_rate(revisions, completed),
        "average_cycle_time_hours": kpi.average(cycle),
    }
