"""Authorisation and data-integrity rules (spec sections 42 and 43).

These are the rules that keep the numbers trustworthy. If any of them stops
holding, the dashboards keep rendering but stop meaning anything -- so each one
gets an explicit test.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest


@pytest.fixture(scope="module")
def sandbox(manager, lead, designer):
    """A throwaway project with a release and two generated tasks."""
    today = date.today()
    products = manager.get("/api/products").json()

    project = manager.post(
        "/api/projects",
        json={
            "name": "Rules Test Project",
            "product_id": products[0]["id"],
            "priority": "Medium",
            "start_date": today.isoformat(),
            "required_completion_date": (today + timedelta(days=45)).isoformat(),
        },
    ).json()

    release = manager.post(
        "/api/releases",
        json={
            "project_id": project["id"],
            "name": "Mechanical Design",
            "release_type": "Mechanical Design",
            "team_lead_id": lead.id,
            "planned_start": today.isoformat(),
            "planned_end": (today + timedelta(days=25)).isoformat(),
        },
    ).json()

    suggestion = manager.get(
        f"/api/releases/{release['id']}/suggested-template"
    ).json()
    tasks = manager.post(
        f"/api/releases/{release['id']}/apply-template",
        json={"template_version_id": suggestion["suggested"]["version_id"]},
    ).json()

    return {"project": project, "release": release, "tasks": tasks}


@pytest.fixture(scope="module")
def time_designer(make_designer):
    """A designer with an empty timesheet, created for this run.

    The overlap rule is real, so these tests need a person whose day is not
    already filled by the demo seed or by a previous run of the suite.
    """
    return make_designer("timerules")


class TestAuthentication:
    def test_unauthenticated_requests_are_rejected(self, client):
        response = client.get("/api/projects")
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "not_authenticated"

    def test_a_bad_token_is_rejected(self, client):
        response = client.get(
            "/api/projects", headers={"Authorization": "Bearer not-a-real-token"}
        )
        assert response.status_code == 401

    def test_login_does_not_reveal_whether_an_email_exists(self, client):
        unknown = client.post(
            "/api/auth/login",
            json={"email": "nobody@designops.dev", "password": "whatever12"},
        )
        wrong = client.post(
            "/api/auth/login",
            json={"email": "arun.prakash@designops.dev", "password": "wrongpass12"},
        )
        assert unknown.status_code == wrong.status_code == 401
        assert unknown.json()["error"]["message"] == wrong.json()["error"]["message"]


class TestRoleBasedAccess:
    def test_designer_cannot_create_a_project(self, designer):
        response = designer.post(
            "/api/projects", json={"name": "Should not exist", "priority": "Low"}
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "permission_denied"

    def test_designer_cannot_read_the_audit_log(self, designer):
        assert designer.get("/api/audit-logs").status_code == 403

    def test_designer_cannot_change_business_rules(self, designer):
        response = designer.put(
            "/api/settings/capacity.thresholds",
            json={"value": {"underutilized": 10, "healthy": 20, "high_load": 30}},
        )
        assert response.status_code == 403

    def test_director_is_read_only_on_operations(self, director):
        """Executive visibility must not come with operational write access."""
        response = director.post(
            "/api/projects", json={"name": "Director cannot create this", "priority": "Low"}
        )
        assert response.status_code == 403

    def test_director_can_see_department_analytics(self, director):
        assert director.get("/api/analytics/department").status_code == 200

    def test_team_lead_cannot_create_a_project(self, lead):
        response = lead.post(
            "/api/projects", json={"name": "Lead cannot create this", "priority": "Low"}
        )
        assert response.status_code == 403

    def test_manager_can_create_a_project(self, manager):
        response = manager.post(
            "/api/projects",
            json={"name": "RBAC probe - manager can create", "priority": "Low"},
        )
        assert response.status_code == 201


class TestTimeIntegrity:
    def test_negative_hours_are_rejected(self, time_designer, sandbox, lead):
        task = sandbox["tasks"][0]
        lead.post(f"/api/tasks/{task['id']}/assign", json={"assigned_to_id": time_designer.id})
        response = time_designer.post(
            "/api/time/entries",
            json={
                "task_id": task["id"],
                "entry_date": date.today().isoformat(),
                "hours": -3,
            },
        )
        assert response.status_code == 422

    def test_zero_hours_are_rejected(self, time_designer, sandbox):
        response = time_designer.post(
            "/api/time/entries",
            json={
                "task_id": sandbox["tasks"][0]["id"],
                "entry_date": date.today().isoformat(),
                "hours": 0,
            },
        )
        assert response.status_code == 422

    def test_future_dates_are_rejected(self, time_designer, sandbox):
        response = time_designer.post(
            "/api/time/entries",
            json={
                "task_id": sandbox["tasks"][0]["id"],
                "entry_date": (date.today() + timedelta(days=1)).isoformat(),
                "hours": 2,
            },
        )
        assert response.status_code == 422

    def test_overlapping_entries_are_rejected(self, time_designer, sandbox, lead):
        """Double-counted hours would inflate actuals and distort efficiency."""
        task = sandbox["tasks"][0]
        lead.post(f"/api/tasks/{task['id']}/assign", json={"assigned_to_id": time_designer.id})
        time_designer.post(f"/api/tasks/{task['id']}/status", json={"status": "In Progress"})

        day = (date.today() - timedelta(days=3)).isoformat()
        first = time_designer.post(
            "/api/time/entries",
            json={
                "task_id": task["id"],
                "entry_date": day,
                "hours": 3,
                "started_at": f"{day}T09:00:00Z",
                "ended_at": f"{day}T12:00:00Z",
            },
        )
        assert first.status_code == 201

        clash = time_designer.post(
            "/api/time/entries",
            json={
                "task_id": task["id"],
                "entry_date": day,
                "hours": 2,
                "started_at": f"{day}T11:00:00Z",
                "ended_at": f"{day}T13:00:00Z",
            },
        )
        assert clash.status_code == 409
        assert clash.json()["error"]["code"] == "business_rule_violation"

    def test_a_designer_cannot_log_time_on_another_persons_task(
        self, time_designer, sandbox, lead, manager
    ):
        task = sandbox["tasks"][3]
        users = manager.get("/api/users", params={"role": "Designer"}).json()["items"]
        other = next(u for u in users if u["id"] != time_designer.id)
        lead.post(f"/api/tasks/{task['id']}/assign", json={"assigned_to_id": other["id"]})

        response = time_designer.post(
            "/api/time/entries",
            json={
                "task_id": task["id"],
                "entry_date": date.today().isoformat(),
                "hours": 1,
            },
        )
        assert response.status_code == 409


class TestWorkflowIntegrity:
    def test_a_task_cannot_start_before_its_prerequisites(self, sandbox, lead, designer):
        """The dependency chain must actually block execution."""
        second = sandbox["tasks"][1]
        lead.post(f"/api/tasks/{second['id']}/assign", json={"assigned_to_id": designer.id})
        response = designer.post(
            f"/api/tasks/{second['id']}/status", json={"status": "In Progress"}
        )
        assert response.status_code == 409
        assert "blocked_by" in response.json()["error"]["details"]

    def test_illegal_status_transitions_are_refused(self, sandbox, lead):
        task = sandbox["tasks"][4]
        response = lead.post(
            f"/api/tasks/{task['id']}/status", json={"status": "Approved"}
        )
        assert response.status_code == 409
        assert "allowed" in response.json()["error"]["details"]

    def test_circular_dependencies_are_refused(self, sandbox, lead):
        first, second = sandbox["tasks"][0], sandbox["tasks"][1]
        # second already depends on first from the template, so the reverse
        # edge would close the loop.
        response = lead.post(
            f"/api/tasks/{first['id']}/dependencies",
            json={"depends_on_task_id": second["id"], "is_blocking": True},
        )
        assert response.status_code == 422
        assert "circular" in response.json()["error"]["message"].lower()

    def test_a_task_cannot_depend_on_itself(self, sandbox, lead):
        task = sandbox["tasks"][0]
        response = lead.post(
            f"/api/tasks/{task['id']}/dependencies",
            json={"depends_on_task_id": task["id"]},
        )
        assert response.status_code == 422

    def test_blocking_requires_a_reason(self, sandbox, lead):
        """A blocker with no stated cause is not actionable by anyone."""
        task = sandbox["tasks"][0]
        response = lead.post(
            f"/api/tasks/{task['id']}/status", json={"status": "Blocked"}
        )
        assert response.status_code == 422

    def test_blocking_with_a_reason_is_accepted(self, sandbox, lead):
        task = sandbox["tasks"][0]
        response = lead.post(
            f"/api/tasks/{task['id']}/status",
            json={"status": "Blocked", "note": "Awaiting the customer's civil drawing."},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "Blocked"
        assert response.json()["blocker_reason"].startswith("Awaiting")


class TestReleaseCompletion:
    def test_completion_is_refused_while_mandatory_tasks_are_open(
        self, sandbox, lead
    ):
        response = lead.post(
            f"/api/releases/{sandbox['release']['id']}/complete", json={}
        )
        assert response.status_code == 409
        assert response.json()["error"]["details"]["blocking_tasks"]

    def test_blockers_are_listed_before_attempting_completion(self, sandbox, lead):
        response = lead.get(
            f"/api/releases/{sandbox['release']['id']}/completion-blockers"
        )
        assert response.status_code == 200
        body = response.json()
        assert body["can_complete_cleanly"] is False
        assert len(body["blocking_tasks"]) > 0

    def test_manager_override_requires_a_reason(self, sandbox, manager):
        response = manager.post(
            f"/api/releases/{sandbox['release']['id']}/complete", json={}
        )
        assert response.status_code == 422

    def test_manager_override_is_recorded_in_the_audit_log(
        self, sandbox, manager, director
    ):
        release_id = sandbox["release"]["id"]
        response = manager.post(
            f"/api/releases/{release_id}/complete",
            json={"override_reason": "Customer accepted the partial scope."},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "Completed"

        logs = director.get(
            "/api/audit-logs",
            params={"entity_type": "design_release", "entity_id": release_id},
        ).json()["items"]
        assert any(row["action"] == "OVERRIDE" for row in logs)


class TestCapacityScoping:
    def test_assignment_board_lists_only_execution_staff(self, manager):
        """Directors and managers hold no tasks and must not be assignable."""
        rows = manager.get("/api/resources/assignment-board").json()
        names = {row["full_name"] for row in rows}
        assert "Rajesh Varma" not in names, "the Director is not an assignee"
        assert "Lakshmi Subramanian" not in names, "the Manager is not an assignee"
        assert "Arun Prakash" in names

    def test_heatmap_excludes_non_executing_roles(self, manager):
        body = manager.get("/api/resources/heatmap").json()
        names = {row["full_name"] for row in body["rows"]}
        assert "Rajesh Varma" not in names
        assert names, "heatmap should still list the design team"

    def test_assignment_board_ranks_by_skill_then_headroom(self, manager):
        rows = manager.get("/api/resources/assignment-board").json()
        with_skill = [r for r in rows if r["has_required_skill"]]
        assert with_skill == rows[: len(with_skill)], (
            "people who have the required skill must sort ahead of those who do not"
        )

    def test_designer_cannot_browse_the_teams_capacity(self, designer):
        """Capacity across other people is a lead/manager view, not a personal one."""
        assert designer.get("/api/resources/capacity").status_code == 403

    def test_designer_can_see_their_own_capacity(self, designer):
        response = designer.get("/api/resources/capacity/me")
        assert response.status_code == 200
        body = response.json()
        assert body["user_id"] == designer.id
        assert body["utilization_band"] in {
            "Underutilized", "Healthy", "High Load", "Overloaded", "No Data",
        }


class TestSettingsValidation:
    def test_performance_weights_must_total_100(self, manager):
        response = manager.put(
            "/api/settings/kpi.performance_weights",
            json={"value": {"productivity": 50, "efficiency": 20, "quality": 10}},
        )
        assert response.status_code == 422
        assert "100" in response.json()["error"]["message"]

    def test_capacity_thresholds_must_increase(self, manager):
        response = manager.put(
            "/api/settings/capacity.thresholds",
            json={"value": {"underutilized": 90, "healthy": 70, "high_load": 100}},
        )
        assert response.status_code == 422

    def test_valid_threshold_change_is_accepted_and_audited(self, manager, director):
        response = manager.put(
            "/api/settings/capacity.thresholds",
            json={"value": {"underutilized": 65, "healthy": 88, "high_load": 100}},
        )
        assert response.status_code == 200
        assert response.json()["value"]["underutilized"] == 65

        # Put it back so later runs start from the documented default.
        manager.put(
            "/api/settings/capacity.thresholds",
            json={"value": {"underutilized": 70, "healthy": 90, "high_load": 100}},
        )

        logs = director.get(
            "/api/audit-logs", params={"entity_code": "capacity.thresholds"}
        ).json()["items"]
        assert logs, "settings changes must be audited"


class TestValidation:
    def test_project_dates_must_be_in_order(self, manager):
        today = date.today()
        response = manager.post(
            "/api/projects",
            json={
                "name": "Backwards dates",
                "start_date": today.isoformat(),
                "required_completion_date": (today - timedelta(days=5)).isoformat(),
            },
        )
        assert response.status_code == 422

    def test_missing_required_fields_produce_field_level_errors(self, manager):
        response = manager.post("/api/projects", json={})
        assert response.status_code == 422
        details = response.json()["error"]["details"]
        assert any(d["field"] == "name" for d in details)

    def test_unknown_task_status_is_rejected(self, lead, sandbox):
        response = lead.post(
            f"/api/tasks/{sandbox['tasks'][0]['id']}/status",
            json={"status": "Teleported"},
        )
        assert response.status_code == 422


class TestDerivedDates:
    """A release's actual dates are derived, never stamped once and forgotten.

    A one-shot stamp is how a release came to claim it started in August while
    its tasks finished in June: the stamp was written before the task
    timestamps were corrected, and nothing recomputed it afterwards.
    """

    def test_release_actual_start_follows_its_earliest_task(
        self, db, sandbox, lead, designer
    ):
        from datetime import datetime

        from app.models.release import DesignRelease
        from app.models.task import Task
        from app.services import rollup_service

        release_id = sandbox["release"]["id"]

        lead.post(f"/api/tasks/{sandbox['tasks'][0]['id']}/assign",
                  json={"assigned_to_id": designer.id})
        designer.post(f"/api/tasks/{sandbox['tasks'][0]['id']}/status",
                      json={"status": "In Progress"})

        release = db.get(DesignRelease, release_id)
        rollup_service.refresh_release(db, release)
        first = release.actual_start
        assert first is not None, "starting a task must date the release"

        # Correct the task to have started earlier, as the seed's backdating
        # does. The release must follow rather than keep the stale date.
        task = db.get(Task, sandbox["tasks"][0]["id"])
        task.started_at = datetime.combine(
            first - timedelta(days=10), datetime.min.time()
        )
        db.flush()

        rollup_service.refresh_release(db, release)
        assert release.actual_start == first - timedelta(days=10)

    def test_no_release_starts_after_it_ends(self, db):
        """The invariant the derived date exists to protect."""
        from sqlalchemy import select

        from app.models.release import DesignRelease

        offenders = [
            r.code
            for r in db.execute(select(DesignRelease)).scalars()
            if r.actual_start and r.actual_end and r.actual_start > r.actual_end
        ]
        assert not offenders, f"releases starting after they end: {offenders}"


class TestAssignmentBoard:
    """Spec section 13: the board has to make "who is free" answerable.

    The failure this guards against is subtle. Deriving the capacity window
    from the task's own planned dates looks reasonable until the task has a
    two-day window: every candidate then has 16 hours of capacity, anyone
    carrying a normal workload reads as 300% utilised, and the bands stop
    distinguishing between a free designer and a drowning one.
    """

    def test_window_is_a_planning_horizon_not_the_task_window(self, lead, sandbox):
        task = sandbox["tasks"][0]
        rows = lead.get(
            "/api/resources/assignment-board", params={"task_id": task["id"]}
        ).json()

        assert rows, "the board must offer candidates"
        # Two working weeks at eight hours is the smallest horizon that lets a
        # normal workload land somewhere other than "overloaded".
        assert all(r["available_hours"] >= 40 for r in rows), (
            "capacity window collapsed to the task's own dates: "
            f"{[(r['full_name'], r['available_hours']) for r in rows]}"
        )

    def test_bands_still_discriminate(self, lead, sandbox):
        """Not everyone should land in the same band."""
        rows = lead.get(
            "/api/resources/assignment-board",
            params={"task_id": sandbox["tasks"][0]["id"]},
        ).json()
        bands = {r["utilization_band"] for r in rows}
        assert bands != {"Overloaded"}, "every candidate reads as overloaded"

    def test_candidates_carry_what_a_lead_needs_to_decide(self, lead, sandbox):
        rows = lead.get(
            "/api/resources/assignment-board",
            params={"task_id": sandbox["tasks"][0]["id"]},
        ).json()
        row = rows[0]
        for field in (
            "full_name",
            "open_tasks",
            "allocated_hours",
            "available_hours",
            "utilization_percent",
            "utilization_band",
            "skills",
            "next_deadline",
            "headroom_hours",
        ):
            assert field in row, f"assignment board is missing {field}"


class TestVocabularyReachability:
    """A role must be able to read the values the API demands of it.

    This has been the most persistent defect class in the project: an endpoint
    requires a value from a configured list, the list sits behind an admin
    permission, and the role being asked for it cannot read it. The form then
    cannot satisfy its own validation and the user has no way forward.
    """

    def test_every_role_can_read_the_workflow_vocabularies(
        self, director, manager, lead, designer
    ):
        for actor in (director, manager, lead, designer):
            response = actor.get("/api/meta/vocabularies")
            assert response.status_code == 200, (
                f"{actor.user['email']} cannot read the vocabularies it must "
                "supply values from"
            )
            body = response.json()
            for field in (
                "delay_reasons",
                "revision_categories",
                "task_types",
                "release_types",
                "project_types",
                "require_delay_reason",
            ):
                assert field in body, f"vocabularies missing {field}"

    def test_designer_still_cannot_read_admin_settings(self, designer):
        """Readable vocabularies must not mean readable configuration."""
        assert designer.get("/api/settings").status_code == 403

    def test_designer_still_cannot_edit_vocabularies(self, designer):
        assert (
            designer.put(
                "/api/settings/workflow.task_types", json={"value": ["Anything"]}
            ).status_code
            == 403
        )


class TestSettingShapeValidation:
    """Malformed vocabularies break the designer's submit path, not the admin's.

    workflow.delay_reasons is read as a list of objects. Saved as a list of
    strings it raises TypeError deep inside the overdue-submit rule, so the
    person who sees the 500 is never the person who caused it.
    """

    def test_delay_reasons_must_be_objects(self, manager):
        response = manager.put(
            "/api/settings/workflow.delay_reasons",
            json={"value": ["Customer Change", "Resource Constraint"]},
        )
        assert response.status_code == 422

    def test_delay_reasons_need_a_valid_accountability(self, manager):
        response = manager.put(
            "/api/settings/workflow.delay_reasons",
            json={"value": [{"value": "Customer Change", "accountability": "Maybe"}]},
        )
        assert response.status_code == 422

    def test_task_types_must_be_strings(self, manager):
        response = manager.put(
            "/api/settings/workflow.task_types",
            json={"value": [{"value": "Drawing"}]},
        )
        assert response.status_code == 422

    def test_a_valid_vocabulary_still_saves(self, manager):
        original = manager.get("/api/settings/workflow.task_types").json()["value"]
        try:
            response = manager.put(
                "/api/settings/workflow.task_types",
                json={"value": ["Drawing", "Calculation", "Checking"]},
            )
            assert response.status_code == 200
        finally:
            manager.put(
                "/api/settings/workflow.task_types", json={"value": original}
            )
