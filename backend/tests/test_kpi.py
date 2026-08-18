"""Unit tests for the central KPI definitions (spec section 45).

These are pure functions, so every edge case the dashboards depend on can be
pinned down cheaply -- particularly the "no data" cases, where returning 0
instead of None would silently turn an unknown into a bad score.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from app.services import kpi


class TestEfficiency:
    def test_under_estimate_scores_above_100(self):
        assert kpi.efficiency(10, 8) == 125.0

    def test_over_estimate_scores_below_100(self):
        assert kpi.efficiency(8, 10) == 80.0

    def test_no_actual_hours_is_unknown_not_zero(self):
        assert kpi.efficiency(10, 0) is None

    def test_handles_none(self):
        assert kpi.efficiency(None, None) is None


class TestVariance:
    def test_overrun_is_positive(self):
        assert kpi.effort_variance(10, 14) == 4.0

    def test_underrun_is_negative(self):
        assert kpi.effort_variance(10, 7) == -3.0

    def test_percent_needs_a_baseline(self):
        assert kpi.effort_variance_percent(0, 5) is None
        assert kpi.effort_variance_percent(10, 12.5) == 25.0


class TestUtilization:
    def test_basic(self):
        assert kpi.utilization(80, 100) == 80.0

    def test_over_capacity_exceeds_100(self):
        assert kpi.utilization(108, 100) == 108.0

    def test_no_capacity_is_unknown(self):
        assert kpi.utilization(10, 0) is None

    def test_bands_come_from_configuration(self):
        thresholds = {"underutilized": 70, "healthy": 90, "high_load": 100}
        assert kpi.utilization_band(50, thresholds) == "Underutilized"
        assert kpi.utilization_band(80, thresholds) == "Healthy"
        assert kpi.utilization_band(95, thresholds) == "High Load"
        assert kpi.utilization_band(108, thresholds) == "Overloaded"
        assert kpi.utilization_band(None, thresholds) == "No Data"

    def test_retuned_bands_change_the_answer(self):
        strict = {"underutilized": 50, "healthy": 75, "high_load": 85}
        assert kpi.utilization_band(80, strict) == "High Load"
        assert kpi.utilization_band(90, strict) == "Overloaded"


class TestDelivery:
    def test_on_time_percent(self):
        assert kpi.on_time_percent(8, 10) == 80.0
        assert kpi.on_time_percent(0, 0) is None

    def test_schedule_variance_positive_means_late(self):
        assert (
            kpi.schedule_variance_days(date(2026, 3, 12), date(2026, 3, 10)) == 2
        )

    def test_delay_is_never_negative(self):
        assert kpi.delay_days(date(2026, 9, 1), True, date(2026, 8, 18)) == 0

    def test_delay_counts_days_past_plan(self):
        assert kpi.delay_days(date(2026, 8, 10), True, date(2026, 8, 18)) == 8

    def test_closed_work_has_no_running_delay(self):
        assert kpi.delay_days(date(2026, 8, 10), False, date(2026, 8, 18)) == 0


class TestQuality:
    def test_rework_percent(self):
        assert kpi.rework_percent(14, 100) == 14.0
        assert kpi.rework_percent(0, 0) is None

    def test_first_pass(self):
        assert kpi.first_pass_approval_percent(72, 100) == 72.0
        assert kpi.first_pass_approval_percent(0, 0) is None


class TestFlow:
    def test_cycle_time(self):
        start = datetime(2026, 8, 1, 9, 0, tzinfo=UTC)
        end = datetime(2026, 8, 3, 15, 0, tzinfo=UTC)
        assert kpi.cycle_time_hours(start, end) == 54.0

    def test_cycle_time_rejects_reversed_stamps(self):
        start = datetime(2026, 8, 3, 9, 0, tzinfo=UTC)
        end = datetime(2026, 8, 1, 9, 0, tzinfo=UTC)
        assert kpi.cycle_time_hours(start, end) is None

    def test_naive_datetimes_are_treated_as_utc(self):
        start = datetime(2026, 8, 1, 9, 0)
        end = datetime(2026, 8, 1, 17, 0)
        assert kpi.cycle_time_hours(start, end) == 8.0

    def test_review_turnaround(self):
        submitted = datetime(2026, 8, 1, 9, 0, tzinfo=UTC)
        reviewed = datetime(2026, 8, 1, 21, 30, tzinfo=UTC)
        assert kpi.review_turnaround_hours(submitted, reviewed) == 12.5

    def test_average_ignores_missing_values(self):
        assert kpi.average([10, None, 20]) == 15.0
        assert kpi.average([None, None]) is None


class _FakeTask:
    def __init__(self, estimated, completion):
        self.estimated_hours = estimated
        self.original_estimated_hours = estimated
        self.completion_percent = completion


class TestCompletion:
    def test_completion_is_weighted_by_effort_not_task_count(self):
        # One 40-hour task done, four 1-hour tasks not started. Counting tasks
        # would say 20%; the honest answer is that most of the work is done.
        tasks = [_FakeTask(40, 100)] + [_FakeTask(1, 0) for _ in range(4)]
        assert kpi.completion_percent_by_effort(tasks) == 90.91

    def test_empty_release_is_zero(self):
        assert kpi.completion_percent_by_effort([]) == 0.0


class TestPerformanceScore:
    WEIGHTS = {
        "productivity": 30,
        "efficiency": 20,
        "quality": 20,
        "on_time": 15,
        "utilization": 10,
        "process_compliance": 5,
    }

    def test_perfect_scores_100(self):
        result = kpi.performance_score(
            weights=self.WEIGHTS,
            productivity_index=100,
            efficiency_percent=100,
            first_pass_percent=100,
            on_time_percent_value=100,
            utilization_percent=100,
            process_compliance_percent=100,
        )
        assert result["score"] == 100.0

    def test_overload_is_penalised_not_rewarded(self):
        """130% utilisation must not score better than 100%."""
        at_capacity = kpi.performance_score(
            weights=self.WEIGHTS,
            productivity_index=80,
            efficiency_percent=90,
            first_pass_percent=90,
            on_time_percent_value=90,
            utilization_percent=100,
            process_compliance_percent=100,
        )
        overloaded = kpi.performance_score(
            weights=self.WEIGHTS,
            productivity_index=80,
            efficiency_percent=90,
            first_pass_percent=90,
            on_time_percent_value=90,
            utilization_percent=130,
            process_compliance_percent=100,
        )
        assert overloaded["score"] < at_capacity["score"]

    def test_missing_components_renormalise_rather_than_score_zero(self):
        """A new joiner with no completed work is not a zero-quality employee."""
        result = kpi.performance_score(
            weights=self.WEIGHTS,
            productivity_index=None,
            efficiency_percent=None,
            first_pass_percent=None,
            on_time_percent_value=None,
            utilization_percent=80,
            process_compliance_percent=None,
        )
        assert result["score"] == 80.0
        assert result["weights_applied"] == {"utilization": 100.0}

    def test_no_data_at_all_scores_nothing(self):
        result = kpi.performance_score(
            weights=self.WEIGHTS,
            productivity_index=None,
            efficiency_percent=None,
            first_pass_percent=None,
            on_time_percent_value=None,
            utilization_percent=None,
            process_compliance_percent=None,
        )
        assert result["score"] is None

    def test_reweighting_changes_the_result(self):
        quality_first = dict(self.WEIGHTS, productivity=5, quality=45)
        base = kpi.performance_score(
            weights=self.WEIGHTS,
            productivity_index=100,
            efficiency_percent=100,
            first_pass_percent=40,
            on_time_percent_value=100,
            utilization_percent=100,
            process_compliance_percent=100,
        )
        strict = kpi.performance_score(
            weights=quality_first,
            productivity_index=100,
            efficiency_percent=100,
            first_pass_percent=40,
            on_time_percent_value=100,
            utilization_percent=100,
            process_compliance_percent=100,
        )
        assert strict["score"] < base["score"]
