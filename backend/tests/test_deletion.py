"""Permanent deletion: who may do it, and what goes with it.

DELETE on a project, release or task used to mean "set status to Cancelled".
It now removes the rows. These tests pin the two things that makes dangerous:
the authority to do it, and the state of everything left behind afterwards.

The roll-up assertions matter more than they look. A project stores actual
hours and completion percent as columns, so deleting a release without
recomputing them leaves the project reporting effort that no longer exists
anywhere in the database -- a number that is wrong in a way no screen can
detect, because nothing else disagrees with it.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.execution import TimeEntry
from app.models.project import Project
from app.models.release import DesignRelease
from app.models.system import AuditLog
from app.models.task import Task


def _make_project(manager, name: str) -> dict:
    response = manager.post(
        "/api/projects",
        json={
            "name": name,
            "project_type": "New Design",
            "priority": "Medium",
            "start_date": date.today().isoformat(),
            "required_completion_date": (date.today() + timedelta(days=30)).isoformat(),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _make_release(manager, project_id: str, name: str) -> dict:
    response = manager.post(
        "/api/releases",
        json={
            "project_id": project_id,
            "name": name,
            "release_type": "Structures",
            "priority": "Medium",
            "planned_start": date.today().isoformat(),
            "planned_end": (date.today() + timedelta(days=14)).isoformat(),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _make_task(manager, release_id: str, name: str, assignee_id: str) -> dict:
    response = manager.post(
        "/api/tasks",
        json={
            "release_id": release_id,
            "name": name,
            "task_type": "3D Drawing",
            "estimated_hours": 8,
            "assigned_to_id": assignee_id,
            "planned_start": date.today().isoformat(),
            "planned_end": (date.today() + timedelta(days=3)).isoformat(),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def scratch(manager, make_designer):
    """A project with one release, one task and four logged hours."""
    stamp = datetime.now(UTC).strftime("%H%M%S%f")
    worker = make_designer(f"del{stamp[-6:]}")

    project = _make_project(manager, f"Deletion fixture {stamp}")
    release = _make_release(manager, project["id"], f"Release {stamp}")
    task = _make_task(manager, release["id"], f"Task {stamp}", worker.id)

    logged = worker.post(
        "/api/time/entries",
        json={
            "task_id": task["id"],
            "entry_date": date.today().isoformat(),
            "hours": 4,
            "description": "fixture work",
        },
    )
    assert logged.status_code == 201, logged.text

    return {"project": project, "release": release, "task": task, "worker": worker}


# ---------------------------------------------------------------------------
# Authority
# ---------------------------------------------------------------------------


def test_manager_may_delete_a_project(manager, scratch, db):
    project_id = scratch["project"]["id"]

    response = manager.delete(f"/api/projects/{project_id}")
    assert response.status_code == 200, response.text

    db.expire_all()
    assert db.get(Project, project_id) is None


def test_lead_may_not_delete_a_project(lead, manager, scratch, db):
    """The Team Lead lost project.delete when delete stopped meaning cancel."""
    project_id = scratch["project"]["id"]

    response = lead.delete(f"/api/projects/{project_id}")
    assert response.status_code == 403, response.text

    db.expire_all()
    assert db.get(Project, project_id) is not None, "the project must survive a 403"


def test_lead_may_not_delete_a_release(lead, scratch, db):
    release_id = scratch["release"]["id"]

    response = lead.delete(f"/api/releases/{release_id}")
    assert response.status_code == 403, response.text

    db.expire_all()
    assert db.get(DesignRelease, release_id) is not None


def test_lead_may_still_delete_a_task(lead, scratch, db):
    """One task is a blast radius a Team Lead is trusted with."""
    task_id = scratch["task"]["id"]

    response = lead.delete(f"/api/tasks/{task_id}")
    assert response.status_code == 200, response.text

    db.expire_all()
    assert db.get(Task, task_id) is None


def test_designer_may_not_delete_anything(designer, scratch):
    for url in (
        f"/api/projects/{scratch['project']['id']}",
        f"/api/releases/{scratch['release']['id']}",
        f"/api/tasks/{scratch['task']['id']}",
    ):
        assert designer.delete(url).status_code == 403, url


# ---------------------------------------------------------------------------
# What goes with it
# ---------------------------------------------------------------------------


def test_deleting_a_project_takes_its_releases_tasks_and_time(manager, scratch, db):
    project_id = scratch["project"]["id"]
    release_id = scratch["release"]["id"]
    task_id = scratch["task"]["id"]

    assert manager.delete(f"/api/projects/{project_id}").status_code == 200

    db.expire_all()
    assert db.get(Project, project_id) is None
    assert db.get(DesignRelease, release_id) is None
    assert db.get(Task, task_id) is None
    remaining = db.execute(
        select(TimeEntry).where(TimeEntry.task_id == task_id)
    ).scalars().all()
    assert remaining == [], "time entries must go with the task"


def test_impact_states_the_numbers_before_deleting(manager, scratch):
    response = manager.get(
        f"/api/projects/{scratch['project']['id']}/deletion-impact"
    )
    assert response.status_code == 200, response.text
    impact = response.json()

    assert impact["entity"] == "project"
    assert impact["releases"] == 1
    assert impact["tasks"] == 1
    assert impact["time_entries"] == 1
    assert impact["logged_hours"] == 4.0


def test_impact_does_not_delete_anything(manager, scratch, db):
    """The preview is a GET, and must stay one."""
    manager.get(f"/api/projects/{scratch['project']['id']}/deletion-impact")
    db.expire_all()
    assert db.get(Project, scratch["project"]["id"]) is not None


# ---------------------------------------------------------------------------
# What is left behind
# ---------------------------------------------------------------------------


def test_deleting_a_release_recomputes_the_project(manager, scratch, db):
    """The project must stop counting hours that no longer exist."""
    project_id = scratch["project"]["id"]

    db.expire_all()
    before = db.get(Project, project_id)
    assert float(before.actual_hours) == pytest.approx(4.0), (
        "fixture should have put four hours on the project"
    )

    assert manager.delete(f"/api/releases/{scratch['release']['id']}").status_code == 200

    db.expire_all()
    after = db.get(Project, project_id)
    assert after is not None, "deleting a release must not delete its project"
    assert float(after.actual_hours) == pytest.approx(0.0)


def test_deleting_a_task_recomputes_the_release(manager, scratch, db):
    release_id = scratch["release"]["id"]

    assert manager.delete(f"/api/tasks/{scratch['task']['id']}").status_code == 200

    db.expire_all()
    release = db.get(DesignRelease, release_id)
    assert release is not None
    assert float(release.actual_hours) == pytest.approx(0.0)


def test_the_audit_entry_outlives_what_it_describes(manager, scratch, db):
    """audit_logs does not foreign-key the entity, on purpose."""
    project_id = scratch["project"]["id"]
    code = scratch["project"]["code"]

    assert manager.delete(f"/api/projects/{project_id}").status_code == 200

    db.expire_all()
    entries = (
        db.execute(
            select(AuditLog)
            .where(AuditLog.entity_code == code, AuditLog.action == "DELETE")
            .order_by(AuditLog.created_at.desc())
        )
        .scalars()
        .all()
    )
    assert entries, "deleting must leave a trace"

    recorded = entries[0]
    assert recorded.entity_type == "project"
    # The counts are the point: the log has to say what went, because nothing
    # else can be consulted afterwards.
    assert recorded.old_value["releases"] == 1
    assert recorded.old_value["tasks"] == 1
    assert recorded.old_value["logged_hours"] == 4.0
