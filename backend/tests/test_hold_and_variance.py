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
    # A release is created in Draft, and Draft cannot go straight to On Hold --
    # pausing something that has not started is meaningless, so the state
    # machine does not allow it. Get it underway first, which is the only state
    # in which holding it says anything.
    for status in ("Planning", "In Progress"):
        moved = manager.post(
            f"/api/releases/{a_task['release']['id']}/status", json={"status": status}
        )
        assert moved.status_code == 200, moved.text

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


def test_finishing_far_over_estimate_requires_a_reason(manager, a_task, make_designer):
    """Ten hours estimated, thirty logged, and no explanation offered."""
    worker = make_designer("overran")
    task = manager.post(
        "/api/tasks",
        json={
            "release_id": a_task["release"]["id"],
            "name": "Overran badly",
            "task_type": "2D Checking",
            "estimated_hours": 10,
            "requires_review": False,
            "assigned_to_id": worker.id,
        },
    ).json()

    manager.post(f"/api/tasks/{task['id']}/status", json={"status": "In Progress"})

    # Thirty hours, but split across two days and on dates of this test's own.
    # A single entry is capped at 16 hours, and an entry with no interval is
    # given 09:00 by the server -- so two entries on one date, or on a date
    # another test used for the same person, are refused as overlapping.
    for offset, hours in ((3, 15), (2, 15)):
        logged = manager.post(
            "/api/time/entries",
            json={
                "task_id": task["id"],
                "user_id": worker.id,
                "entry_date": (date.today() - timedelta(days=offset)).isoformat(),
                "hours": hours,
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


def test_finishing_close_to_estimate_needs_no_explanation(manager, a_task, make_designer):
    """The rule must not nag about ordinary drift."""
    worker = make_designer("ontarget")
    task = manager.post(
        "/api/tasks",
        json={
            "release_id": a_task["release"]["id"],
            "name": "Ran about as expected",
            "task_type": "Concept",
            "estimated_hours": 10,
            "requires_review": False,
            "assigned_to_id": worker.id,
        },
    ).json()

    manager.post(f"/api/tasks/{task['id']}/status", json={"status": "In Progress"})
    manager.post(
        "/api/time/entries",
        json={
            "task_id": task["id"],
            "user_id": worker.id,
            "entry_date": date.today().isoformat(),
            "hours": 11,
            "description": "About right",
        },
    )

    done = manager.post(f"/api/tasks/{task['id']}/status", json={"status": "Completed"})
    assert done.status_code == 200, done.text


def test_finishing_far_under_estimate_also_asks_why(manager, a_task, make_designer):
    """An estimate that was twice too big is as wrong as one twice too small."""
    worker = make_designer("underran")
    task = manager.post(
        "/api/tasks",
        json={
            "release_id": a_task["release"]["id"],
            "name": "Finished very early",
            "task_type": "Concept",
            "estimated_hours": 20,
            "requires_review": False,
            "assigned_to_id": worker.id,
        },
    ).json()

    manager.post(f"/api/tasks/{task['id']}/status", json={"status": "In Progress"})
    manager.post(
        "/api/time/entries",
        json={
            "task_id": task["id"],
            "user_id": worker.id,
            # Its own date, so it cannot overlap another test's entry.
            "entry_date": (date.today() - timedelta(days=5)).isoformat(),
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
        "/api/time/entries",
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


def test_a_task_planned_past_the_release_moves_the_target(db, manager, a_task):
    """The release date follows the work, and the movement is recorded.

    This used to assert tasks_past_release_date. It cannot any more, and that
    is the system being better rather than the rule being wrong: adding a task
    beyond the release end now extends the release to cover it, so there is no
    task sitting past the date. What is worth saying instead is that the target
    moved from what was originally committed, which is the thing a manager
    needs to see.
    """
    release_id = a_task["release"]["id"]
    before = manager.get(f"/api/releases/{release_id}").json()["planned_end"]

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
    assert detail["planned_end"] > before, "the release should have been extended"

    codes = [r["code"] for r in detail["health_reasons"]]
    assert "target_moved_from_baseline" in codes, detail["health_reasons"]


def test_a_release_pulled_in_past_its_tasks_says_so(manager, a_task):
    """The other direction: the date moves and the work does not.

    Extension keeps tasks inside the release when work is added, so the only
    way to end up with tasks past the date is to bring the date forward. That
    is a real thing a manager does under pressure, and the release should say
    plainly that the plan no longer closes.
    """
    release = manager.post(
        "/api/releases",
        json={
            "project_id": a_task["project"]["id"],
            "name": "Pulled in later",
            "release_type": "Design Release",
            "planned_start": date.today().isoformat(),
            "planned_end": (date.today() + timedelta(days=30)).isoformat(),
        },
    ).json()

    # Comfortably inside the release, so nothing is extended on the way in.
    created = manager.post(
        "/api/tasks",
        json={
            "release_id": release["id"],
            "name": "Runs to the twentieth",
            "task_type": "Check Sheet Filling",
            "estimated_hours": 4,
            "planned_end": (date.today() + timedelta(days=20)).isoformat(),
            "requires_review": False,
        },
    )
    assert created.status_code == 201, created.text

    pulled = manager.patch(
        f"/api/releases/{release['id']}",
        json={"planned_end": (date.today() + timedelta(days=10)).isoformat()},
    )
    assert pulled.status_code == 200, pulled.text

    detail = manager.get(f"/api/releases/{release['id']}").json()
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
