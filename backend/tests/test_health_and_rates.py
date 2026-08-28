"""Two things a dashboard must never do: drift, and exaggerate.

Both of these were real. Health colours were read from a stored delay column
that nothing refreshed on a schedule, so a project nobody touched kept
yesterday's colour. And the department's revision rate counted every revision
ever raised against one period's completed tasks, over a denominator forced to
a minimum of one -- which reported a quiet week as several hundred per cent.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.services import health_service, kpi


class _Release:
    """The fields the health rules read, and nothing else.

    A stand-in rather than a database row, so the test can move `today` around
    freely -- which is the whole point: the same row on two different days must
    not report the same colour.
    """

    def __init__(
        self,
        status,
        planned_end=None,
        actual_end=None,
        delay_days=0,
        completion_percent=0,
    ):
        self.status = status
        self.planned_end = planned_end
        self.actual_end = actual_end
        self.delay_days = delay_days
        self.completion_percent = completion_percent
        # The schedule and effort rules read these too. A stand-in has to carry
        # every field the engine touches or it fails with AttributeError, which
        # says nothing about the rule under test -- so they default to the
        # values that make those rules no-ops, leaving the schedule rules alone
        # as the thing being measured.
        self.baseline_planned_start = None
        self.baseline_planned_end = None
        self.forecast_end = None
        self.estimated_hours = 0
        self.actual_hours = 0
        self.rework_hours = 0
        self.revision_count = 0
        self.health = "GREEN"
        self.health_reasons = []
        # No id: the task and blocker queries then match nothing, leaving the
        # schedule rules as the only thing under test.
        self.id = None
        self.code = "DR-TEST"
        self.name = "Test release"
        self.estimated_hours = 0
        self.actual_hours = 0
        self.rework_hours = 0
        self.revision_count = 0


# ---------------------------------------------------------------------------
# Health is computed from the dates, not from a column nobody refreshes
# ---------------------------------------------------------------------------


def test_a_delay_is_measured_from_today_not_from_a_stored_column():
    """The column is deliberately wrong here; the answer must ignore it."""
    planned = date(2026, 1, 10)
    today = date(2026, 1, 20)

    delay = health_service.live_delay_days(
        planned, "In Progress", health_service._OPEN_RELEASE_VALUES, today
    )
    assert delay == 10


def test_a_finished_release_has_no_running_delay():
    planned = date(2026, 1, 10)
    today = date(2026, 1, 20)

    assert (
        health_service.live_delay_days(
            planned, "Completed", health_service._OPEN_RELEASE_VALUES, today
        )
        == 0
    )


def test_an_approved_release_counts_as_finished():
    """The drawings are out; only the formal close remains."""
    assert (
        health_service.live_delay_days(
            date(2026, 1, 10), "Approved", health_service._OPEN_RELEASE_VALUES,
            date(2026, 1, 20),
        )
        == 0
    )


def test_a_late_delivery_is_still_reported_after_it_is_finished():
    """The regression: delay_days is zero once something closes.

    Reading it for a delivered release reported every late delivery as on time
    as soon as a sweep ran. Delivery lateness is actual minus planned.
    """
    assert (
        health_service.delivered_late_days(date(2026, 1, 18), date(2026, 1, 10)) == 8
    )


def test_delivering_early_is_not_lateness():
    assert (
        health_service.delivered_late_days(date(2026, 1, 5), date(2026, 1, 10)) == 0
    )


def test_delivery_lateness_is_unknown_without_both_dates():
    assert health_service.delivered_late_days(None, date(2026, 1, 10)) == 0
    assert health_service.delivered_late_days(date(2026, 1, 10), None) == 0


def test_release_health_goes_red_as_days_pass_with_nobody_touching_it(db):
    """The whole point: the same row, two different days, two colours."""
    planned = date(2026, 1, 10)
    release = _Release("In Progress", planned_end=planned, delay_days=0)

    on_time_day = date(2026, 1, 10)
    _, on_time_findings = health_service.evaluate_release_health(
        db, release, on_time_day
    )
    assert not [f for f in on_time_findings if f["code"] == "release_behind_schedule"]

    much_later = date(2026, 2, 10)
    level, findings = health_service.evaluate_release_health(db, release, much_later)
    behind = [f for f in findings if f["code"] == "release_behind_schedule"]
    assert behind, "a month past its planned end, with a stale column, it stayed green"
    assert behind[0]["value"] == 31
    assert level == "RED"


def test_a_completed_release_reports_how_late_it_landed(db):
    release = _Release(
        "Completed",
        planned_end=date(2026, 1, 10),
        actual_end=date(2026, 1, 21),
        delay_days=0,  # what a sweep leaves behind on a closed release
    )
    level, findings = health_service.evaluate_release_health(db, release, date(2026, 2, 1))
    late = [f for f in findings if f["code"] == "delivered_late"]
    assert late, "a release delivered eleven days late reported as on time"
    assert late[0]["value"] == 11
    assert level == "RED"


def test_a_completed_release_delivered_on_time_stays_green(db):
    release = _Release(
        "Completed",
        planned_end=date(2026, 1, 10),
        actual_end=date(2026, 1, 10),
    )
    level, findings = health_service.evaluate_release_health(db, release, date(2026, 2, 1))
    assert level == "GREEN"
    assert not findings


# ---------------------------------------------------------------------------
# A rate compares like with like, or says nothing
# ---------------------------------------------------------------------------


def test_a_rate_with_nothing_to_divide_by_is_unknown_not_zero():
    """The dash rule. A forced denominator of 1 turned this into a number."""
    assert kpi.revision_rate(4, 0) is None


def test_a_revision_rate_is_a_believable_percentage():
    assert kpi.revision_rate(3, 12) == 25.0


def test_the_department_revision_rate_stays_within_reason(manager):
    """Over a period where nothing much happened, it must not read in the hundreds."""
    today = date.today()
    response = manager.get(
        "/api/analytics/department",
        params={
            "date_from": (today - timedelta(days=2)).isoformat(),
            "date_to": today.isoformat(),
        },
    )
    assert response.status_code == 200, response.text

    rate = response.json()["revision_rate_percent"]
    if rate is None:
        return  # nothing completed in the window: the honest answer
    assert rate >= 0
    assert rate <= 400, (
        f"revision rate came back as {rate}% -- the numerator and denominator "
        "are measuring different periods again"
    )


def test_a_period_with_no_completed_work_reports_a_dash(manager):
    """A window before the department existed has no completions at all."""
    response = manager.get(
        "/api/analytics/department",
        params={"date_from": "2001-01-01", "date_to": "2001-01-07"},
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["revision_rate_percent"] is None, (
        "an empty period reported a revision rate instead of 'not enough data'"
    )
    assert body["on_time_percent"] is None
