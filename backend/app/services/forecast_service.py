"""When we now expect things to finish, as distinct from when we promised.

Four kinds of date, and the whole model is keeping them apart:

    commitment   what design promised   frozen, changed only deliberately
    target       what a phase aims at   a plan, may be revised
    forecast     what we now expect     derived, disposable, moves daily
    actual       what happened          observed, never typed

The forecast deliberately uses no effort data. This department plans in
milestone dates and always has -- their tracker is a wall of dates, not a
resource model -- and a forecast built on estimated hours would need 1,076
estimates that do not exist and a working habit nobody has. So:

    a finished phase       forecasts at the date it actually finished
    an unfinished phase    forecasts at max(its target, today)
    no target, unfinished  contributes nothing, and says so

That last line matters. A release whose phases carry no dates has no forecast
at all, and the honest answer is a dash rather than a number invented from
today. The same rule the rest of the system already follows: not enough data
is not the same as zero.

Taking max(target, today) is what makes the forecast move on its own. A phase
due last Tuesday that nobody has touched forecasts at today and slides forward
every morning, instead of sitting frozen at a date already gone and reporting
a project as on track while it quietly stops.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import OPEN_TASK_STATUSES, TaskStatus
from app.models.project import Project
from app.models.release import DesignRelease
from app.models.task import Task

_OPEN_TASK_VALUES = {s.value for s in OPEN_TASK_STATUSES}
_DONE_TASK_VALUES = {TaskStatus.COMPLETED.value, TaskStatus.APPROVED.value}

#: The phase design is accountable for handing over. Measured against dispatch,
#: packing and stuffing land around and after it, so dispatch was never
#: design's deadline -- this is.
HANDOVER_PHASE = "Mfg. Release"


@dataclass(frozen=True, slots=True)
class Outlook:
    """What a release or project is currently expected to do."""

    commitment: date | None
    forecast: date | None

    @property
    def variance_days(self) -> int | None:
        """Positive means late. None means we cannot say, which is not zero."""
        if self.commitment is None or self.forecast is None:
            return None
        return (self.forecast - self.commitment).days

    @property
    def float_days(self) -> int | None:
        """Days of room left before the commitment is at risk."""
        variance = self.variance_days
        return None if variance is None else -variance

    @property
    def state(self) -> str:
        variance = self.variance_days
        if variance is None:
            return "Unknown"
        if variance > 0:
            return "Forecast Late"
        if variance > -7:
            return "At Risk"
        return "On Track"


def forecast_release(db: Session, release: DesignRelease, today: date | None = None) -> date | None:
    """The date this release is now expected to be handed over.

    The latest of its phases' own forecasts. Phases that are finished report
    when they finished; phases still open report the later of their target and
    today, because a target in the past is not a forecast.
    """
    today = today or date.today()
    tasks = db.execute(select(Task).where(Task.release_id == release.id)).scalars().all()

    if not tasks:
        return None

    dates: list[date] = []
    for task in tasks:
        if task.status in _DONE_TASK_VALUES:
            if task.completed_at:
                dates.append(task.completed_at.date())
            continue
        if task.status not in _OPEN_TASK_VALUES:
            continue  # cancelled work is not waiting on anybody
        if task.planned_end:
            dates.append(max(task.planned_end, today))

    return max(dates) if dates else None


def refresh_release_forecast(
    db: Session, release: DesignRelease, today: date | None = None
) -> Outlook:
    release.forecast_end = forecast_release(db, release, today)
    return Outlook(commitment=release.planned_end, forecast=release.forecast_end)


def refresh_project_forecast(
    db: Session, project: Project, today: date | None = None
) -> Outlook:
    """The latest forecast among the releases that gate completion.

    Releases marked as not completion-critical are excluded: a late Ceiling
    Supports does not hold a project the way a late Structures does, and
    treating every release as gating overstates risk on exactly the projects
    carrying the most releases.
    """
    today = today or date.today()
    releases = db.execute(
        select(DesignRelease).where(
            DesignRelease.project_id == project.id,
            DesignRelease.is_completion_critical.is_(True),
        )
    ).scalars().all()

    forecasts = [r.forecast_end for r in releases if r.forecast_end]
    project.forecast_end = max(forecasts) if forecasts else None
    return Outlook(
        commitment=project.required_completion_date, forecast=project.forecast_end
    )


def suggest_phase_targets(
    db: Session, project: Project, handover: date
) -> dict[str, date]:
    """Phase dates for a new release, offered from this project's own history.

    Deliberately per-project. Across the whole department the offsets are
    useless -- 3D Design has run anywhere from 9 to 68 days ahead of dispatch --
    because a 613-car Sycamore does not schedule like a 22-car Ganga. Within
    one project they are worth something.

    Returned as a suggestion for a person to accept or overwrite. A schedule
    generated from a median and presented as fact is worse than a blank one:
    it looks authoritative, it is usually wrong, and people stop reading it.
    """
    rows = db.execute(
        select(Task.name, Task.planned_end, DesignRelease.planned_end)
        .join(DesignRelease, DesignRelease.id == Task.release_id)
        .where(
            DesignRelease.project_id == project.id,
            Task.planned_end.is_not(None),
            DesignRelease.planned_end.is_not(None),
        )
    ).all()

    offsets: dict[str, list[int]] = {}
    for name, task_end, release_end in rows:
        offsets.setdefault(name, []).append((release_end - task_end).days)

    suggestions: dict[str, date] = {}
    for name, values in offsets.items():
        values.sort()
        median = values[len(values) // 2]
        suggestions[name] = handover - __import__("datetime").timedelta(days=median)
    return suggestions
