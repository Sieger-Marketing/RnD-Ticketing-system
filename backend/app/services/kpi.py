"""Central KPI definitions (spec section 45).

Every formula in the product is defined exactly once, here, as a pure
function. Routes, dashboards, reports and the seed script all call these --
nothing recomputes a metric inline, and the frontend never does arithmetic on
raw rows. Changing the definition of "efficiency" is a one-line change in this
file and it propagates everywhere.

Design notes that repeat across the module:

* Division by zero returns None, not 0. "No data" and "zero percent" are
  different answers and a dashboard must be able to tell them apart.
* Percentages are returned as numbers out of 100, rounded to two decimals.
* Nothing here touches the database, so all of it is directly unit-testable.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime
from decimal import Decimal


def _f(value: float | Decimal | None) -> float:
    """Coerce Numeric/None into a float without exploding on None."""
    if value is None:
        return 0.0
    return float(value)


def _pct(numerator: float, denominator: float) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator * 100, 2)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


# ---------------------------------------------------------------------------
# Effort
# ---------------------------------------------------------------------------


def efficiency(planned_hours, actual_hours) -> float | None:
    """Planned / Actual x 100.

    Above 100 means the work took less than planned. Returns None when no
    hours have been logged -- a task nobody has worked on has no efficiency,
    which is not the same as being 0% efficient.
    """
    return _pct(_f(planned_hours), _f(actual_hours))


def effort_variance(planned_hours, actual_hours) -> float:
    """Actual - Planned. Positive means overrun."""
    return round(_f(actual_hours) - _f(planned_hours), 2)


def effort_variance_percent(planned_hours, actual_hours) -> float | None:
    planned = _f(planned_hours)
    if planned == 0:
        return None
    return round((_f(actual_hours) - planned) / planned * 100, 2)


# ---------------------------------------------------------------------------
# Capacity
# ---------------------------------------------------------------------------


def utilization(allocated_hours, available_hours) -> float | None:
    """Allocated / Available x 100."""
    return _pct(_f(allocated_hours), _f(available_hours))


def utilization_band(util: float | None, thresholds: dict) -> str:
    """Map a utilisation percentage onto its configured band.

    Thresholds arrive from app_settings, never from a constant here, so a
    manager can retune the bands without a deploy (spec section 12).
    """
    if util is None:
        return "No Data"
    under = float(thresholds.get("underutilized", 70))
    healthy = float(thresholds.get("healthy", 90))
    high = float(thresholds.get("high_load", 100))
    if util < under:
        return "Underutilized"
    if util < healthy:
        return "Healthy"
    if util <= high:
        return "High Load"
    return "Overloaded"


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------


def on_time_percent(completed_on_time: int, completed_total: int) -> float | None:
    """Completed on time / Completed x 100."""
    return _pct(completed_on_time, completed_total)


def schedule_variance_days(
    actual_completion: date | None, planned_completion: date | None
) -> int | None:
    """Actual - Planned, in days. Positive means late."""
    if actual_completion is None or planned_completion is None:
        return None
    return (actual_completion - planned_completion).days


def delay_days(planned_end: date | None, status_is_open: bool, today: date) -> int:
    """Days an open item is past its planned end. Never negative.

    A finished item has no delay by this measure -- use schedule_variance_days
    for the retrospective view of something already delivered.
    """
    if planned_end is None or not status_is_open:
        return 0
    return max((today - planned_end).days, 0)


def is_overdue(planned_end: date | None, status_is_open: bool, today: date) -> bool:
    return planned_end is not None and status_is_open and today > planned_end


# ---------------------------------------------------------------------------
# Quality
# ---------------------------------------------------------------------------


def rework_percent(rework_hours, total_actual_hours) -> float | None:
    """Rework hours / Total actual hours x 100."""
    return _pct(_f(rework_hours), _f(total_actual_hours))


def first_pass_approval_percent(
    approved_first_round: int, total_submitted: int
) -> float | None:
    """Approved without any revision / Total submitted x 100."""
    return _pct(approved_first_round, total_submitted)


def revision_rate(revision_count: int, task_count: int) -> float | None:
    """Revisions per completed task, as a percentage."""
    return _pct(revision_count, task_count)


# ---------------------------------------------------------------------------
# Flow
# ---------------------------------------------------------------------------


def cycle_time_hours(
    started_at: datetime | None, completed_at: datetime | None
) -> float | None:
    """Completion - Start, in hours."""
    start, end = _aware(started_at), _aware(completed_at)
    if start is None or end is None or end < start:
        return None
    return round((end - start).total_seconds() / 3600, 2)


def queue_time_hours(
    assigned_at: datetime | None, started_at: datetime | None
) -> float | None:
    """Start - Assignment, in hours. How long work waited before being picked up."""
    assigned, start = _aware(assigned_at), _aware(started_at)
    if assigned is None or start is None or start < assigned:
        return None
    return round((start - assigned).total_seconds() / 3600, 2)


def review_turnaround_hours(
    submitted_at: datetime | None, reviewed_at: datetime | None
) -> float | None:
    """Review completion - Review submission, in hours."""
    submitted, reviewed = _aware(submitted_at), _aware(reviewed_at)
    if submitted is None or reviewed is None or reviewed < submitted:
        return None
    return round((reviewed - submitted).total_seconds() / 3600, 2)


def average(values: Iterable[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    if not present:
        return None
    return round(sum(present) / len(present), 2)


# ---------------------------------------------------------------------------
# Progress
# ---------------------------------------------------------------------------


def completion_percent_by_effort(tasks: Iterable) -> float:
    """Effort-weighted completion, not a task count.

    A release whose one 40-hour task is done and whose four 1-hour tasks are
    not is 91% complete, not 20%. Counting tasks would systematically
    misreport progress on releases with uneven task sizes (spec section 48).
    """
    total_weight = 0.0
    done_weight = 0.0
    for task in tasks:
        weight = max(
            _f(getattr(task, "estimated_hours", 0))
            or _f(getattr(task, "original_estimated_hours", 0)),
            0.5,
        )
        total_weight += weight
        done_weight += weight * (_f(getattr(task, "completion_percent", 0)) / 100.0)
    if total_weight == 0:
        return 0.0
    return round(done_weight / total_weight * 100, 2)


# ---------------------------------------------------------------------------
# Performance score (spec section 19)
# ---------------------------------------------------------------------------


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def performance_score(
    *,
    weights: dict,
    productivity_index: float | None,
    efficiency_percent: float | None,
    first_pass_percent: float | None,
    on_time_percent_value: float | None,
    utilization_percent: float | None,
    process_compliance_percent: float | None,
) -> dict:
    """Weighted 0-100 score plus the component breakdown.

    Two deliberate choices:

    * Components with no data are dropped and the remaining weights are
      renormalised, so a new joiner with no completed tasks is not scored as
      zero on quality.
    * Utilisation scores highest at 100% and is penalised symmetrically in
      both directions -- being at 130% is a problem, not an achievement, and
      rewarding it would incentivise exactly the overload the capacity engine
      exists to prevent.
    """
    utilization_component = None
    if utilization_percent is not None:
        utilization_component = _clamp(100 - abs(100 - utilization_percent))

    components: dict[str, float | None] = {
        "productivity": None
        if productivity_index is None
        else _clamp(productivity_index),
        "efficiency": None
        if efficiency_percent is None
        else _clamp(efficiency_percent),
        "quality": None if first_pass_percent is None else _clamp(first_pass_percent),
        "on_time": None
        if on_time_percent_value is None
        else _clamp(on_time_percent_value),
        "utilization": utilization_component,
        "process_compliance": None
        if process_compliance_percent is None
        else _clamp(process_compliance_percent),
    }

    usable = {k: v for k, v in components.items() if v is not None}
    total_weight = sum(float(weights.get(k, 0)) for k in usable)
    if total_weight == 0:
        return {"score": None, "components": components, "weights_applied": {}}

    applied = {k: float(weights.get(k, 0)) / total_weight for k in usable}
    score = sum(usable[k] * applied[k] for k in usable)

    return {
        "score": round(score, 2),
        "components": {k: (None if v is None else round(v, 2)) for k, v in components.items()},
        "weights_applied": {k: round(v * 100, 2) for k, v in applied.items()},
    }


def productivity_index(
    completed_effort_weight: float, available_hours: float
) -> float | None:
    """Effort-weighted output per available hour, expressed against a 100 base.

    Effort-weighted rather than task-counted: one 20-hour complex task and ten
    2-hour trivial ones should not read as a 10x productivity difference
    (spec section 48). 100 means the person delivered weighted output equal to
    their available hours.
    """
    if available_hours <= 0:
        return None
    return round(completed_effort_weight / available_hours * 100, 2)
