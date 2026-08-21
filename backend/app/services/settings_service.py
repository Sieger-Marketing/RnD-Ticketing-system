"""Runtime-configurable business rules.

Everything the spec says a manager must be able to tune -- capacity bands, KPI
weights, health rules, delay reasons, revision categories, working hours --
is read through here. No engine hard-codes a threshold; they all call
`get_setting`, which falls back to the documented default when the row is
absent so a fresh database still behaves sensibly.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.system import AppSetting

# ---------------------------------------------------------------------------
# Defaults. These seed the app_settings table and act as the fallback if a row
# is deleted. Changing a value here changes it only for databases that have
# never been seeded; live systems are edited through the Settings API.
# ---------------------------------------------------------------------------

DEFAULT_SETTINGS: dict[str, tuple[str, Any, str]] = {
    # -- capacity (spec section 12) ---------------------------------------
    "capacity.thresholds": (
        "capacity",
        {"underutilized": 70, "healthy": 90, "high_load": 100},
        "Utilisation band edges in percent. <underutilized is under-used, "
        "underutilized..healthy is healthy, healthy..high_load is high load, "
        "above high_load is overloaded.",
    ),
    "capacity.standard_daily_hours": (
        "capacity",
        8,
        "Default productive hours per working day when a user has no override.",
    ),
    "capacity.working_days": (
        "capacity",
        [0, 1, 2, 3, 4],
        "Working days of the week, Monday=0.",
    ),
    # -- KPI weights (spec section 19) ------------------------------------
    "kpi.performance_weights": (
        "kpi",
        {
            "productivity": 30,
            "efficiency": 20,
            "quality": 20,
            "on_time": 15,
            "utilization": 10,
            "process_compliance": 5,
        },
        "Performance score weights in percent. Must total 100.",
    ),
    "kpi.efficiency_target": (
        "kpi",
        100,
        "Efficiency percent considered on-plan. 100 means actual equalled planned.",
    ),
    "kpi.rework_warning_percent": (
        "kpi",
        10,
        "Rework percentage above which a team or project is flagged.",
    ),
    "kpi.first_pass_target_percent": (
        "kpi",
        85,
        "First-pass approval percentage below which quality is flagged.",
    ),
    # -- project health (spec section 21) ---------------------------------
    "health.rules": (
        "health",
        {
            "amber_delay_days": 2,
            "red_delay_days": 5,
            "amber_overdue_tasks": 1,
            "red_overdue_tasks": 3,
            "amber_effort_overrun_percent": 10,
            "red_effort_overrun_percent": 25,
            "amber_utilization_percent": 100,
            "red_utilization_percent": 110,
            "amber_rework_percent": 10,
            "red_rework_percent": 20,
            "amber_blocked_tasks": 1,
            "red_blocked_tasks": 3,
            "deadline_proximity_days": 7,
        },
        "Thresholds the health engine uses to decide GREEN / AMBER / RED.",
    ),
    # -- workflow vocabularies (spec sections 16, 20, 34) -----------------
    "workflow.hold_reasons": (
        "workflow",
        [
            "Customer Instruction",
            "Awaiting Approval",
            "Awaiting Drawing Input",
            "Design Change Expected",
            "Commercial Hold",
            "Resource Reallocated",
            "Site Not Ready",
            "Other",
        ],
        "Why work was deliberately paused. Distinct from a blocker, which is "
        "waiting on something specific rather than parked by a decision.",
    ),
    #: Why the time taken differed materially from the estimate. Separate from
    #: a delay reason: a task can finish on time and still take twice the
    #: hours, and that is the number the next estimate should learn from.
    "workflow.variance_reasons": (
        "workflow",
        [
            "Scope Grew",
            "Underestimated",
            "Rework",
            "Waiting Time Included",
            "Complexity Higher Than Expected",
            "Learning Curve",
            "Finished Faster Than Expected",
            "Other",
        ],
        "Why the hours taken differed materially from the estimate. Separate "
        "from a delay reason: work can finish on time and still cost double.",
    ),
    "workflow.require_variance_reason": (
        "workflow",
        True,
        "Whether finishing work whose hours drifted materially from the "
        "estimate must carry a reason.",
    ),
    #: How far actual may drift from estimate before a reason is required.
    "workflow.variance_threshold_percent": (
        "workflow",
        25,
        "How far actual hours may drift from the estimate, either way, before "
        "a reason is required.",
    ),
    "workflow.delay_reasons": (
        "workflow",
        [
            {"value": "Resource Constraint", "accountability": "Controllable"},
            {"value": "Dependency", "accountability": "Controllable"},
            {"value": "Waiting for Input", "accountability": "External"},
            {"value": "Waiting for Approval", "accountability": "External"},
            {"value": "Customer Change", "accountability": "External"},
            {"value": "Technical Issue", "accountability": "Controllable"},
            {"value": "Rework", "accountability": "Controllable"},
            {"value": "Priority Change", "accountability": "External"},
            {"value": "Capacity", "accountability": "Controllable"},
            {"value": "Other", "accountability": "Controllable"},
        ],
        "Delay reasons and whether each is the department's fault.",
    ),
    "workflow.revision_categories": (
        "workflow",
        [
            {"value": "Design Error", "accountability": "Controllable"},
            {"value": "Customer Change", "accountability": "External"},
            {"value": "Scope Change", "accountability": "External"},
            {"value": "Engineering Change", "accountability": "External"},
            {"value": "Manufacturing Feedback", "accountability": "External"},
            {"value": "Incorrect Input", "accountability": "External"},
            {"value": "Missing Information", "accountability": "External"},
            {"value": "Internal Review", "accountability": "Controllable"},
            {"value": "Other", "accountability": "Controllable"},
        ],
        "Revision categories and whether each counts as controllable rework.",
    ),
    "workflow.release_types": (
        "workflow",
        [
            "Concept / Layout",
            "Mechanical Design",
            "Electrical Design",
            "Detailed Design",
            "Manufacturing Drawing",
            "BOM",
            "Final Documentation",
        ],
        "Design release types available when creating a release.",
    ),
    "workflow.task_types": (
        "workflow",
        [
            "Drawing",
            "Layout",
            "Calculation",
            "Modelling",
            "Simulation",
            "BOM",
            "Checking",
            "Documentation",
            "Revision",
            "Coordination",
        ],
        "Task types.",
    ),
    "workflow.project_types": (
        "workflow",
        ["New Product", "Customisation", "Repeat Order", "Retrofit", "Study"],
        "Project types.",
    ),
    "workflow.require_delay_reason": (
        "workflow",
        True,
        "Whether an overdue item must carry a delay reason before it can move on.",
    ),
    # -- notifications (spec section 29) ----------------------------------
    "notifications.due_soon_days": (
        "notifications",
        2,
        "How many days ahead a task counts as due soon.",
    ),
    "notifications.email_enabled": (
        "notifications",
        False,
        "Whether notifications also go out by email.",
    ),
}


def get_setting(db: Session, key: str, default: Any = None) -> Any:
    """Read a setting, falling back to the documented default."""
    row = db.execute(
        select(AppSetting).where(AppSetting.key == key)
    ).scalar_one_or_none()
    if row is not None:
        return row.value
    if key in DEFAULT_SETTINGS:
        return DEFAULT_SETTINGS[key][1]
    return default


def set_setting(db: Session, key: str, value: Any, updated_by_id=None) -> AppSetting:
    row = db.execute(
        select(AppSetting).where(AppSetting.key == key)
    ).scalar_one_or_none()
    if row is None:
        category = DEFAULT_SETTINGS.get(key, ("custom",))[0]
        row = AppSetting(
            key=key, category=category, value=value, is_system=key in DEFAULT_SETTINGS
        )
        db.add(row)
    else:
        row.value = value
    row.updated_by_id = updated_by_id
    db.flush()
    return row


def ensure_defaults(db: Session) -> int:
    """Insert any default setting that is missing. Returns how many were added."""
    existing = {
        k for (k,) in db.execute(select(AppSetting.key)).all()
    }
    added = 0
    for key, (category, value, description) in DEFAULT_SETTINGS.items():
        if key in existing:
            continue
        db.add(
            AppSetting(
                key=key,
                category=category,
                value=value,
                description=description,
                is_system=True,
            )
        )
        added += 1
    if added:
        db.flush()
    return added


# ---------------------------------------------------------------------------
# Typed convenience readers used by the engines
# ---------------------------------------------------------------------------


def capacity_thresholds(db: Session) -> dict[str, float]:
    return get_setting(db, "capacity.thresholds")


def health_rules(db: Session) -> dict[str, float]:
    return get_setting(db, "health.rules")


def performance_weights(db: Session) -> dict[str, float]:
    return get_setting(db, "kpi.performance_weights")


def working_days(db: Session) -> set[int]:
    return set(get_setting(db, "capacity.working_days"))


def accountability_for(db: Session, key: str, value: str) -> str:
    """Look up whether a delay reason or revision category is controllable."""
    for item in get_setting(db, key) or []:
        if isinstance(item, dict) and item.get("value") == value:
            return item.get("accountability", "Controllable")
    return "Controllable"
