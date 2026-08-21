"""Pausing work, and explaining why it took what it took.

Three rules, each of which exists because the absence of it loses something
that cannot be recovered later: why work stopped, why it cost what it did, and
whether the plan was ever capable of closing.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.core.enums import TaskStatus
from app.services import health_service


@pytest.fixture(scope="module")
def a_task(manager, lead):
    """A task of our own, so nothing here disturbs real work."""
    customers = manager.get("/api/customers").json()["items"]
    products = manager.get("/api/products").json()
    today = date.today()

    project = manager.post(
        "/api/projects",
        json={
            "name": "Hold Test Project",
            "customer_id": customers[0]["id"] if customers else None,
            "product_id": products[0]["id"] if products else None,
            "project_type": "New Design",
            "priority": "Medium",
            "start_date": today.isoformat(),
            "required_completion_date": (today + timedelta(days=30)).isoformat(),
        },
    ).json()

    release = manager.post(
        "/api/releases",
        json={
            "project_id": project["id"],
            "name": "Hold Test Release",
            "release_type": "Design Release",
            "planned_start": today.isoformat(),
            "planned_end": (today + timedelta(days=10)).isoformat(),
        },
    ).json()

    task = manager.post(
        "/api/tasks",
        json={
            "release_id": release["id"],
            "name": "Held work",
            "task_type": "3D Drawing",
            "estimated_hours": 10,
            "planned_start": today.isoformat(),
            "planned_end": (today + timedelta(days=5)).isoformat(),
            "requires_review": False,
            "assigned_to_id": lead.id,
        },
    )
    assert task.status_code == 201, task.text
    return {"project": project, "release": release, "task": task.json()}


# ---------------------------------------------------------------------------
# Putting work on hold
# ---------------------------------------------------------------------------


def test_a_task_can_be_put_on_hold(manager, a_task):
    response = manager.post(
        f"/api/tasks/{a_task['task']['id']}/status",
        json={"status": "On Hold", "hold_reason": "Awaiting Approval"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == TaskStatus.ON_HOLD.value
    assert response.json()["hold_reason"] == "Awaiting Approval"


def test_a_hold_without_a_reason_is_refused(manager, a_task, lead):
    """Work that stops for no recorded reason reads later as forgotten."""
    task = manager.post(
        "/api/tasks",
        json={
            "release_id": a_task["release"]["id"],
            "name": "Unexplained hold",
            "task_type": "2D Drawing",
            "estimated_hours": 4,
            "requires_review": False,
            "assigned_to_id": lead.id,
        },
    ).json()

    response = manager.post(
        f"/api/tasks/{task['id']}/status", json={"status": "On Hold"}
    )
    assert response.status_code == 422, response.text
    assert "reason" in response.json()["error"]["message"].lower()
    assert response.json()["error"]["details"]["allowed_reasons"]


def test_held_work_comes_back_to_where_it_was(manager, a_task):
    """A held task resumes; it does not jump forward to review."""
    task_id = a_task["task"]["id"]
    back = manager.post(
        f"/api/tasks/{task_id}/status", json={"status": "In Progress"}
    )
    assert back.status_code == 200, back.text

    manager.post(
        f"/api/tasks/{task_id}/status",
        json={"status": "On Hold", "hold_reason": "Commercial Hold"},
    )
    jump = manager.post(
        f"/api/tasks/{task_id}/status", json={"status": "Submitted for Review"}
    )
    assert jump.status_code == 409, jump.text

    manager.post(f"/api/tasks/{task_id}/status", json={"status": "In Progress"})


def test_a_release_and_a_project_can_be_held(manager, a_task):
    release = manager.post(
        f"/api/releases/{a_task['release']['id']}/status",
        json={"status": "On Hold"},
    )
    assert release.status_code == 200, release.text
    assert release.json()["status"] == "On Hold"

    project = manager.patch(
        f"/api/projects/{a_task['project']['id']}", json={"status": "On Hold"}
    )
    assert project.status_code == 200, project.text
    assert project.json()["status"] == "On Hold"

    # Put them back so the rest of the module works against live statuses.
    manager.post(
        f"/api/releases/{a_task['release']['id']}/status",
        json={"status": "In Progress"},
    )
    manager.patch(
        f"/api/projects/{a_task['project']['id']}",
        json={"status": "Design In Progress"},
    )


# ---------------------------------------------------------------------------
# Explaining the hours
# ---------------------------------------------------------------------------


def test_finishing_far_over_estimate_requires_a_reason(manager, a_task, lead):
    """Ten hours estimated, thirty logged, and no explanation offered."""
    task = manager.post(
        "/api/tasks",
        json={
            "release_id": a_task["release"]["id"],
            "name": "Overran badly",
            "task_type": "2D Checking",
            "estimated_hours": 10,
            "requires_review": False,
            "assigned_to_id": lead.id,
        },
    ).json()

    manager.post(f"/api/tasks/{task['id']}/status", json={"status": "In Progress"})
    logged = manager.post(
        "/api/time-entries",
        json={
            "task_id": task["id"],
            "user_id": lead.id,
            "entry_date": date.today().isoformat(),
            "hours": 30,
            "description": "Took far longer than planned",
        },
    )
    assert logged.status_code == 201, logged.text

    refused = manager.post(
        f"/api/tasks/{task['id']}/status", json={"status": "Completed"}
    )
    assert refused.status_code == 422, refused.text
    details = refused.json()["error"]["details"]
    assert details["variance_percent"] == 200.0
    assert details["allowed_reasons"]

    accepted = manager.post(
        f"/api/tasks/{task['id']}/status",
        json={"status": "Completed", "variance_reason": "Scope Grew"},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["variance_reason"] == "Scope Grew"


def test_finishing_close_to_estimate_needs_no_explanation(manager, a_task, lead):
    """The rule must not nag about ordinary drift."""
    task = manager.post(
        "/api/tasks",
        json={
            "release_id": a_task["release"]["id"],
            "name": "Ran about as expected",
            "task_type": "Concept",
            "estimated_hours": 10,
            "requires_review": False,
            "assigned_to_id": lead.id,
        },
    ).json()

    manager.post(f"/api/tasks/{task['id']}/status", json={"status": "In Progress"})
    manager.post(
        "/api/time-entries",
        json={
            "task_id": task["id"],
            "user_id": lead.id,
            "entry_date": date.today().isoformat(),
            "hours": 11,
            "description": "About right",
        },
    )

    done = manager.post(f"/api/tasks/{task['id']}/status", json={"status": "Completed"})
    assert done.status_code == 200, done.text


def test_finishing_far_under_estimate_also_asks_why(manager, a_task, lead):
    """An estimate that was twice too big is as wrong as one twice too small."""
    task = manager.post(
        "/api/tasks",
        json={
            "release_id": a_task["release"]["id"],
            "name": "Finished very early",
            "task_type": "Concept",
            "estimated_hours": 20,
            "requires_review": False,
            "assigned_to_id": lead.id,
        },
    ).json()

    manager.post(f"/api/tasks/{task['id']}/status", json={"status": "In Progress"})
    manager.post(
        "/api/time-entries",
        json={
            "task_id": task["id"],
            "user_id": lead.id,
            "entry_date": date.today().isoformat(),
            "hours": 4,
            "description": "Much simpler than expected",
        },
    )

    refused = manager.post(
        f"/api/tasks/{task['id']}/status", json={"status": "Completed"}
    )
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"]["details"]["variance_percent"] == -80.0


def test_a_task_with_no_estimate_is_not_asked(manager, a_task, lead):
    """Nothing to vary from; the question would be meaningless."""
    task = manager.post(
        "/api/tasks",
        json={
            "release_id": a_task["release"]["id"],
            "name": "No estimate given",
            "task_type": "Concept",
            "estimated_hours": 0,
            "requires_review": False,
            "assigned_to_id": lead.id,
        },
    ).json()

    manager.post(f"/api/tasks/{task['id']}/status", json={"status": "In Progress"})
    manager.post(
        "/api/time-entries",
        json={
            "task_id": task["id"],
            "user_id": lead.id,
            "entry_date": date.today().isoformat(),
            "hours": 6,
            "description": "Unplanned work",
        },
    )
    done = manager.post(f"/api/tasks/{task['id']}/status", json={"status": "Completed"})
    assert done.status_code == 200, done.text


# ---------------------------------------------------------------------------
# Dates that do not add up
# ---------------------------------------------------------------------------


class _Release:
    def __init__(self, planned_end):
        self.status = "In Progress"
        self.planned_end = planned_end
        self.actual_end = None
        self.delay_days = 0
        self.completion_percent = 0
        self.id = None
        self.code = "DR-TEST"
        self.name = "Test"
        self.estimated_hours = 0
        self.actual_hours = 0
        self.rework_hours = 0
        self.revision_count = 0


def test_a_release_whose_tasks_run_past_it_says_so(db, manager, a_task):
    """The plan cannot close, and it should say so on the day it is made."""
    release_id = a_task["release"]["id"]

    # A task planned well beyond the release's own end date.
    manager.post(
        "/api/tasks",
        json={
            "release_id": release_id,
            "name": "Planned past the release",
            "task_type": "Check Sheet Filling",
            "estimated_hours": 4,
            "planned_end": (date.today() + timedelta(days=40)).isoformat(),
            "requires_review": False,
        },
    )

    detail = manager.get(f"/api/releases/{release_id}").json()
    codes = [r["code"] for r in detail["health_reasons"]]
    assert "tasks_past_release_date" in codes, detail["health_reasons"]


def test_a_release_planned_past_the_project_date_says_so(manager, a_task):
    project_id = a_task["project"]["id"]

    manager.post(
        "/api/releases",
        json={
            "project_id": project_id,
            "name": "Lands after the project is due",
            "release_type": "Design Release",
            "planned_end": (date.today() + timedelta(days=200)).isoformat(),
        },
    )

    detail = manager.get(f"/api/projects/{project_id}").json()
    codes = [r["code"] for r in detail["health_reasons"]]
    assert "release_planned_past_project_date" in codes, detail["health_reasons"]
