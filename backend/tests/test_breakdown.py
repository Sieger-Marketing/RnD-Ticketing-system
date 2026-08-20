"""Performance cut by product, customer and team, and drilled into.

The value of one implementation behind three lenses is that the lenses cannot
disagree. These tests hold that: whatever line the rows are cut along, the
department totals underneath them are the same numbers.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.db.session import SessionLocal
from app.services import breakdown_service

PERIOD = {"date_from": "2025-01-01", "date_to": date.today().isoformat()}

ROW_FIELDS = {
    "key",
    "label",
    "projects",
    "releases",
    "tasks_completed",
    "tasks_open",
    "tasks_overdue",
    "planned_hours",
    "actual_hours",
    "rework_hours",
    "efficiency_percent",
    "effort_variance_hours",
    "on_time_percent",
    "rework_percent",
    "first_pass_approval_percent",
    "revision_rate_percent",
    "average_cycle_time_hours",
    "health",
}


@pytest.mark.parametrize("dimension", ["product", "customer", "team", "project"])
def test_every_lens_returns_the_same_shaped_rows(manager, dimension):
    """One table, one set of columns, whatever it is cut by."""
    response = manager.get(
        "/api/analytics/breakdown", params={"dimension": dimension, **PERIOD}
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["dimension"] == dimension
    assert body["row_label"]
    for row in body["rows"]:
        assert set(row) == ROW_FIELDS, f"{dimension} rows have a different shape"


def test_the_department_totals_do_not_depend_on_how_you_slice_them(manager):
    """The same work, grouped differently, is still the same work."""
    totals = {}
    for dimension in ["product", "customer", "team"]:
        body = manager.get(
            "/api/analytics/breakdown", params={"dimension": dimension, **PERIOD}
        ).json()
        totals[dimension] = body["totals"]

    baseline = totals["product"]
    for dimension, figures in totals.items():
        assert figures["tasks_completed"] == baseline["tasks_completed"], dimension
        assert figures["actual_hours"] == baseline["actual_hours"], dimension
        assert figures["planned_hours"] == baseline["planned_hours"], dimension
        assert figures["efficiency_percent"] == baseline["efficiency_percent"], dimension


def test_totals_are_recomputed_not_averaged(manager):
    """An average of percentages weights four hours like four hundred."""
    body = manager.get(
        "/api/analytics/breakdown", params={"dimension": "product", **PERIOD}
    ).json()

    planned = sum(r["planned_hours"] for r in body["rows"])
    actual = sum(r["actual_hours"] for r in body["rows"])
    assert body["totals"]["planned_hours"] == pytest.approx(planned, abs=0.05)
    assert body["totals"]["actual_hours"] == pytest.approx(actual, abs=0.05)

    if actual:
        expected = round(planned / actual * 100, 2)
        assert body["totals"]["efficiency_percent"] == pytest.approx(expected, abs=0.05)


def test_work_nobody_classified_is_shown_rather_than_dropped(manager):
    """A project with no product is exactly the work that goes unnoticed."""
    body = manager.get(
        "/api/analytics/breakdown", params={"dimension": "product", **PERIOD}
    ).json()
    labels = [r["label"] for r in body["rows"]]

    unlabelled = [r for r in body["rows"] if r["key"] is None]
    if unlabelled:
        assert unlabelled[0]["label"] == breakdown_service.UNASSIGNED, labels


def test_a_drill_down_only_contains_what_is_under_it(manager):
    """The regression: health ignored the drill-down and returned everything."""
    products = manager.get(
        "/api/analytics/breakdown", params={"dimension": "product", **PERIOD}
    ).json()
    target = next((r for r in products["rows"] if r["key"]), None)
    if target is None:
        pytest.skip("no classified product in this dataset")

    drilled = manager.get(
        "/api/analytics/breakdown",
        params={
            "dimension": "project",
            "within_dimension": "product",
            "within_key": target["key"],
            **PERIOD,
        },
    ).json()

    assert drilled["within"] == {"dimension": "product", "key": target["key"]}

    # Every project returned must really carry that product.
    with SessionLocal() as db:
        from sqlalchemy import select

        from app.models.project import Project

        for row in drilled["rows"]:
            if not row["key"]:
                continue
            product_id = db.execute(
                select(Project.product_id).where(Project.id == row["key"])
            ).scalar()
            assert str(product_id) == target["key"], (
                f"{row['label']} is not a {target['label']} project"
            )


def test_a_drill_down_never_exceeds_the_whole(manager):
    """A part cannot be larger than what it is part of."""
    products = manager.get(
        "/api/analytics/breakdown", params={"dimension": "product", **PERIOD}
    ).json()
    target = next((r for r in products["rows"] if r["key"]), None)
    if target is None:
        pytest.skip("no classified product in this dataset")

    drilled = manager.get(
        "/api/analytics/breakdown",
        params={
            "dimension": "project",
            "within_dimension": "product",
            "within_key": target["key"],
            **PERIOD,
        },
    ).json()

    assert drilled["totals"]["tasks_completed"] == target["tasks_completed"]
    assert drilled["totals"]["actual_hours"] == pytest.approx(
        target["actual_hours"], abs=0.05
    )


def test_a_period_with_nothing_in_it_says_so_rather_than_zero(manager):
    body = manager.get(
        "/api/analytics/breakdown",
        params={"dimension": "product", "date_from": "2001-01-01", "date_to": "2001-01-07"},
    ).json()

    totals = body["totals"]
    assert totals["tasks_completed"] == 0
    assert totals["efficiency_percent"] is None
    assert totals["on_time_percent"] is None
    assert totals["first_pass_approval_percent"] is None


def test_an_unknown_dimension_is_refused(manager):
    response = manager.get(
        "/api/analytics/breakdown", params={"dimension": "colour", **PERIOD}
    )
    assert response.status_code == 422, response.text


def test_a_designer_cannot_read_the_department_breakdown(designer):
    response = designer.get(
        "/api/analytics/breakdown", params={"dimension": "product", **PERIOD}
    )
    assert response.status_code == 403, response.text


# ---------------------------------------------------------------------------
# The exportable form of the same table
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fmt", ["json", "csv", "xlsx", "pdf"])
def test_the_breakdown_exports_in_every_format(manager, fmt):
    response = manager.get(
        "/api/reports/breakdown", params={"dimension": "product", "format": fmt}
    )
    assert response.status_code == 200, response.text
    assert len(response.content) > 0
    if fmt != "json":
        assert "attachment" in response.headers.get("content-disposition", "")


def test_the_report_and_the_screen_agree(manager):
    """A figure argued over in a meeting must match the one on the dashboard."""
    today = date.today()
    start = today - timedelta(days=30)
    params = {"date_from": start.isoformat(), "date_to": today.isoformat()}

    screen = manager.get(
        "/api/analytics/breakdown", params={"dimension": "product", **params}
    ).json()
    report = manager.get(
        "/api/reports/breakdown",
        params={"dimension": "product", "format": "json", **params},
    ).json()

    summary = {item["label"]: item["value"] for item in report["summary"]}
    assert summary["Tasks completed"] == screen["totals"]["tasks_completed"]
    assert summary["Efficiency %"] == screen["totals"]["efficiency_percent"]
    assert summary["On time %"] == screen["totals"]["on_time_percent"]


def test_the_report_is_listed_so_the_screen_can_find_it(manager):
    """A report nothing lists is a report nobody can reach."""
    catalogue = manager.get("/api/reports").json()
    keys = {r["key"] for r in catalogue["reports"]}
    assert "breakdown" in keys
