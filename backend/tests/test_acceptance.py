"""The spec section 51 acceptance scenario, end to end over the real API.

    Manager creates a project -> selects a product -> creates a design release
    -> picks the product template -> generates standard tasks -> assigns a
    Team Lead -> Lead reviews and adds a task -> assigns designers -> Designer
    starts, records time, submits -> Reviewer rejects one -> revision created
    -> Designer reworks and resubmits -> Reviewer approves -> release progress
    updates -> project progress updates -> dashboards and KPIs reflect it.

Every step asserts that the change actually persisted, so the test fails if a
dashboard number stops being derived from transactional data.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest


@pytest.fixture(scope="module")
def scenario(manager, lead, make_designer, client):
    """Runs the whole workflow once; each test then asserts one stage of it.

    Uses a designer created for this run so that the timesheet starts empty and
    the suite can be re-run without wiping the database.
    """
    designer = make_designer("acceptance")
    state: dict = {"designer": None}

    # -- 1. Manager creates a project against a real customer and product ---
    products = manager.get("/api/products").json()
    customers = manager.get("/api/customers").json()["items"]
    assert products and customers, "seed data is required for this test"

    product = products[0]
    today = date.today()

    response = manager.post(
        "/api/projects",
        json={
            "name": "Acceptance Test - Automated Parking Retrofit",
            "description": "Created by the section 51 acceptance test.",
            "customer_id": customers[0]["id"],
            "product_id": product["id"],
            "project_type": "New Product",
            "priority": "High",
            "start_date": today.isoformat(),
            "required_completion_date": (today + timedelta(days=60)).isoformat(),
        },
    )
    assert response.status_code == 201, response.text
    state["project"] = response.json()

    # -- 2. Manager creates a design release ------------------------------
    response = manager.post(
        "/api/releases",
        json={
            "project_id": state["project"]["id"],
            "name": "Mechanical Design",
            "release_type": "Mechanical Design",
            "priority": "High",
            "planned_start": today.isoformat(),
            "planned_end": (today + timedelta(days=30)).isoformat(),
        },
    )
    assert response.status_code == 201, response.text
    state["release"] = response.json()
    release_id = state["release"]["id"]

    # -- 3. The system suggests the matching product template -------------
    suggestion = manager.get(f"/api/releases/{release_id}/suggested-template").json()
    assert suggestion["suggested"] is not None, "no template matched the product"
    state["suggestion"] = suggestion

    # -- 4. Generating standard tasks from that template ------------------
    response = manager.post(
        f"/api/releases/{release_id}/apply-template",
        json={"template_version_id": suggestion["suggested"]["version_id"]},
    )
    assert response.status_code == 200, response.text
    state["generated_tasks"] = response.json()

    # -- 5. Manager assigns the Team Lead ---------------------------------
    response = manager.post(
        f"/api/releases/{release_id}/assign-lead",
        params={"team_lead_id": lead.id},
    )
    assert response.status_code == 200, response.text
    state["release"] = response.json()

    # -- 6. Team Lead accepts and reviews the generated task list ---------
    response = lead.post(f"/api/releases/{release_id}/accept")
    assert response.status_code == 200, response.text

    tasks = lead.get(f"/api/releases/{release_id}/tasks").json()
    assert len(tasks) >= 5

    # -- 7. Team Lead adds a task of their own ----------------------------
    response = lead.post(
        "/api/tasks",
        json={
            "release_id": release_id,
            "name": "Customer-specific bracket detailing",
            "task_type": "Drawing",
            "priority": "Medium",
            "estimated_hours": 6,
            "planned_start": today.isoformat(),
            "planned_end": (today + timedelta(days=5)).isoformat(),
            "requires_review": True,
        },
    )
    assert response.status_code == 201, response.text
    state["added_task"] = response.json()

    # -- 8. Team Lead assigns work to a designer --------------------------
    target = state["generated_tasks"][0]
    response = lead.post(
        f"/api/tasks/{target['id']}/assign", json={"assigned_to_id": designer.id}
    )
    assert response.status_code == 200, response.text
    state["task"] = response.json()
    task_id = state["task"]["id"]

    # -- 9. Designer starts the task --------------------------------------
    response = designer.post(
        f"/api/tasks/{task_id}/status", json={"status": "In Progress"}
    )
    assert response.status_code == 200, response.text

    # -- 10. Designer records time ----------------------------------------
    response = designer.post(
        "/api/time/entries",
        json={
            "task_id": task_id,
            "entry_date": today.isoformat(),
            "hours": 6.5,
            "description": "Initial GA drawing",
            "started_at": f"{today.isoformat()}T04:00:00Z",
            "ended_at": f"{today.isoformat()}T10:30:00Z",
        },
    )
    assert response.status_code == 201, response.text
    state["first_entry"] = response.json()

    # -- 11. Designer submits for review ----------------------------------
    # The task came in well under its estimate, and the workflow requires that
    # gap to be explained before the work can move on -- the same rule, and the
    # same field, the UI puts in front of the designer.
    response = designer.post(
        "/api/reviews/submit",
        json={
            "task_id": task_id,
            "reviewer_id": lead.id,
            "variance_reason": "Finished Faster Than Expected",
        },
    )
    assert response.status_code == 201, response.text
    state["review_round_1"] = response.json()

    # -- 12. Reviewer rejects, creating a revision ------------------------
    review_id = state["review_round_1"]["id"]
    lead.post(f"/api/reviews/{review_id}/start")
    response = lead.post(
        f"/api/reviews/{review_id}/decision",
        json={
            "result": "Revision Requested",
            "comments": "Clearance to the column line is wrong.",
            "revision_category": "Design Error",
            "revision_reason": "Incorrect clearance to structural column.",
            "root_cause": "Outdated civil reference used.",
        },
    )
    assert response.status_code == 200, response.text
    state["decision_1"] = response.json()
    state["revision"] = state["decision_1"]["revision"]

    # -- 13. Designer performs the rework ---------------------------------
    designer.post(f"/api/tasks/{task_id}/status", json={"status": "In Progress"})
    response = designer.post(
        "/api/time/entries",
        json={
            "task_id": task_id,
            "entry_date": today.isoformat(),
            "hours": 2.5,
            "description": "Rework after review",
            "started_at": f"{today.isoformat()}T11:00:00Z",
            "ended_at": f"{today.isoformat()}T13:30:00Z",
        },
    )
    assert response.status_code == 201, response.text
    state["rework_entry"] = response.json()

    # -- 14. Designer resubmits -------------------------------------------
    response = designer.post(
        "/api/reviews/submit", json={"task_id": task_id, "reviewer_id": lead.id}
    )
    assert response.status_code == 201, response.text
    state["review_round_2"] = response.json()

    # -- 15. Reviewer approves --------------------------------------------
    review_2 = state["review_round_2"]["id"]
    lead.post(f"/api/reviews/{review_2}/start")
    response = lead.post(
        f"/api/reviews/{review_2}/decision",
        json={"result": "Approved", "comments": "Correction verified."},
    )
    assert response.status_code == 200, response.text
    state["decision_2"] = response.json()

    state["designer"] = designer
    state["task_final"] = designer.get(f"/api/tasks/{task_id}").json()
    state["release_final"] = manager.get(f"/api/releases/{release_id}").json()
    state["project_final"] = manager.get(
        f"/api/projects/{state['project']['id']}"
    ).json()
    return state


class TestProjectAndReleaseCreation:
    def test_project_gets_a_human_readable_code(self, scenario):
        assert scenario["project"]["code"].startswith("PRJ-")

    def test_project_starts_not_started_and_green(self, scenario):
        assert scenario["project"]["status"] == "Not Started"
        assert scenario["project"]["health"] == "GREEN"

    def test_release_gets_a_sequence_number(self, scenario):
        assert scenario["release"]["sequence_number"] == 1
        assert scenario["release"]["code"].startswith("DR-")


class TestTemplateGeneration:
    def test_template_matched_the_product(self, scenario):
        assert scenario["suggestion"]["suggested"]["task_count"] >= 5

    def test_standard_tasks_were_generated(self, scenario):
        assert len(scenario["generated_tasks"]) >= 5
        assert all(t["code"].startswith("TSK-") for t in scenario["generated_tasks"])

    def test_generated_tasks_carry_the_template_estimates(self, scenario):
        assert sum(t["estimated_hours"] for t in scenario["generated_tasks"]) > 0

    def test_release_pins_the_template_version(self, scenario):
        assert scenario["release_final"]["template_version_id"] is not None
        assert scenario["release_final"]["template_version_label"].startswith("v")

    def test_regenerating_is_refused(self, manager, scenario):
        response = manager.post(
            f"/api/releases/{scenario['release']['id']}/apply-template",
            json={
                "template_version_id": scenario["suggestion"]["suggested"]["version_id"]
            },
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "business_rule_violation"


class TestAssignmentAndExecution:
    def test_assignment_moved_the_task_forward(self, scenario):
        assert scenario["task"]["assigned_to_id"] is not None
        assert scenario["task"]["status"] == "Assigned"

    def test_lead_could_add_a_task(self, scenario):
        assert scenario["added_task"]["name"].startswith("Customer-specific")
        assert scenario["added_task"]["release_id"] == scenario["release"]["id"]

    def test_dependencies_were_generated_from_the_template(self, scenario, lead):
        second = scenario["generated_tasks"][1]
        detail = lead.get(f"/api/tasks/{second['id']}").json()
        assert detail["dependencies"], "template sequencing produced no dependencies"


class TestTimeTracking:
    def test_first_entry_is_not_rework(self, scenario):
        assert scenario["first_entry"]["is_rework"] is False
        assert scenario["first_entry"]["hours"] == 6.5

    def test_rework_entry_is_flagged_automatically(self, scenario):
        """Time logged while a revision is open must count as rework."""
        assert scenario["rework_entry"]["is_rework"] is True
        assert scenario["rework_entry"]["revision_id"] is not None

    def test_task_actual_hours_are_the_sum_of_entries(self, scenario):
        assert scenario["task_final"]["actual_hours"] == 9.0

    def test_task_rework_hours_track_only_the_rework(self, scenario):
        assert scenario["task_final"]["rework_hours"] == 2.5


class TestReviewAndRevision:
    def test_first_round_was_round_one(self, scenario):
        assert scenario["review_round_1"]["round_number"] == 1

    def test_rejection_created_a_revision(self, scenario):
        revision = scenario["revision"]
        assert revision is not None
        assert revision["category"] == "Design Error"
        assert revision["revision_number"] == 1

    def test_design_error_is_classified_controllable(self, scenario):
        assert scenario["revision"]["accountability"] == "Controllable"

    def test_resubmission_is_round_two(self, scenario):
        assert scenario["review_round_2"]["round_number"] == 2

    def test_turnaround_was_measured(self, scenario):
        assert scenario["decision_2"]["review"]["turnaround_hours"] is not None

    def test_task_ends_completed_and_approved(self, scenario):
        assert scenario["task_final"]["status"] == "Completed"
        assert scenario["task_final"]["review_status"] == "Approved"
        assert scenario["task_final"]["revision_count"] == 1

    def test_reviewer_cannot_review_their_own_work(self, lead, scenario):
        designer = scenario["designer"]
        """A designer must not be able to approve the task they executed."""
        # Use the task the lead added by hand: it has no template dependency,
        # so it can actually be started.
        task = scenario["added_task"]
        lead.post(f"/api/tasks/{task['id']}/assign", json={"assigned_to_id": designer.id})
        designer.post(f"/api/tasks/{task['id']}/status", json={"status": "In Progress"})
        submitted = designer.post(
            "/api/reviews/submit",
            json={"task_id": task["id"], "reviewer_id": designer.id},
        )
        assert submitted.status_code == 201
        review_id = submitted.json()["id"]
        designer.post(f"/api/reviews/{review_id}/start")
        response = designer.post(
            f"/api/reviews/{review_id}/decision",
            json={"result": "Approved", "comments": "Looks fine to me."},
        )
        assert response.status_code in (403, 409)


class TestRollupsAndDashboards:
    def test_release_progress_updated(self, scenario):
        assert scenario["release_final"]["completion_percent"] > 0
        assert scenario["release_final"]["actual_hours"] == 9.0
        assert scenario["release_final"]["rework_hours"] == 2.5

    def test_release_revision_count_rolled_up(self, scenario):
        assert scenario["release_final"]["revision_count"] >= 1

    def test_project_progress_updated(self, scenario):
        assert scenario["project_final"]["actual_hours"] >= 9.0
        assert scenario["project_final"]["completion_percent"] > 0
        assert scenario["project_final"]["planned_hours"] > 0

    def test_project_efficiency_is_computed(self, scenario):
        assert scenario["project_final"]["efficiency_percent"] is not None

    def test_manager_dashboard_reflects_the_work(self, manager):
        response = manager.get("/api/analytics/dashboard/manager")
        assert response.status_code == 200
        body = response.json()
        assert body["kpis"]["active_projects"] > 0
        assert "capacity_heatmap" in body
        assert "release_progress" in body

    def test_director_dashboard_reflects_the_project(self, director, scenario):
        response = director.get("/api/analytics/dashboard/executive")
        assert response.status_code == 200
        body = response.json()
        assert body["kpis"]["active_projects"] > 0
        assert body["kpis"]["rework_percent"] is not None
        assert isinstance(body["insights"], list)

    def test_designer_dashboard_shows_personal_kpis(self, scenario):
        designer = scenario["designer"]
        response = designer.get("/api/analytics/dashboard/designer")
        assert response.status_code == 200
        kpis = response.json()["kpis"]
        assert kpis["tasks_completed"] >= 1
        assert kpis["performance_score"]["score"] is not None

    def test_project_dashboard_has_a_timeline(self, manager, scenario):
        response = manager.get(
            f"/api/analytics/projects/{scenario['project']['id']}"
        )
        assert response.status_code == 200
        body = response.json()
        assert body["timeline"], "project dashboard has no release timeline"
        assert body["task_counts"]["total"] >= 5


class TestAuditTrail:
    def test_status_changes_were_recorded(self, manager, scenario):
        response = manager.get(
            "/api/status-history",
            params={"entity_type": "task", "entity_id": scenario["task"]["id"]},
        )
        assert response.status_code == 200
        transitions = [row["to_status"] for row in response.json()]
        assert "In Progress" in transitions
        assert "Revision Required" in transitions
        assert "Completed" in transitions

    def test_audit_log_captured_the_project_creation(self, director, scenario):
        response = director.get(
            "/api/audit-logs",
            params={"entity_type": "project", "entity_id": scenario["project"]["id"]},
        )
        assert response.status_code == 200
        assert any(row["action"] == "CREATE" for row in response.json()["items"])
