"""Make planned_end mean what design is accountable for.

Until now a release's planned_end held the DISPATCH date, taken straight from
the tracker. Measured against it, packing and stuffing land a median of thirty
days AFTER it and a third of all phase dates fall past it -- which is not a
department missing its deadlines, it is the wrong deadline. Dispatch is when
the system ships. Design hands over at Mfg. Release, weeks earlier.

Every delay figure, every health colour and every on-time percentage reads
planned_end, so correcting the column corrects all of them at once.

This moves three things:

  dispatch_date  <- whatever planned_end held (the shipping date, kept)
  planned_end    <- the Mfg. Release phase target (design's commitment)
  baseline_*     <- stamped from the corrected dates, which the two import
                    routes never did, leaving every imported release unable to
                    report that its target had moved

Where a release has no Mfg. Release target, planned_end is left empty rather
than guessed. A release with no committed handover date should say so.

Safe by default: prints what it would change. Pass --apply.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal  # noqa: E402
from app.models.release import DesignRelease  # noqa: E402
from app.models.task import Task  # noqa: E402
from app.services import forecast_service  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the changes")
    args = parser.parse_args()

    with SessionLocal() as db:
        releases = db.execute(select(DesignRelease)).scalars().all()

        moved_dispatch = 0
        set_commitment = 0
        no_handover = 0
        stamped = 0

        for release in releases:
            # 1. The date currently in planned_end is the dispatch date.
            if release.planned_end and release.dispatch_date is None:
                if args.apply:
                    release.dispatch_date = release.planned_end
                moved_dispatch += 1

            # 2. Design's commitment is the Mfg. Release phase target.
            handover = db.execute(
                select(Task.planned_end).where(
                    Task.release_id == release.id,
                    Task.name == forecast_service.HANDOVER_PHASE,
                    Task.planned_end.is_not(None),
                )
            ).scalar()

            if handover:
                if args.apply:
                    release.planned_end = handover
                set_commitment += 1
            else:
                # Nothing to commit to. Better empty than the wrong date.
                if args.apply:
                    release.planned_end = None
                no_handover += 1

            # 3. Stamp the baseline the import routes never did.
            if args.apply:
                if release.planned_start and release.baseline_planned_start is None:
                    release.baseline_planned_start = release.planned_start
                if release.planned_end and release.baseline_planned_end is None:
                    release.baseline_planned_end = release.planned_end
                    stamped += 1

        if args.apply:
            db.flush()
            for release in releases:
                forecast_service.refresh_release_forecast(db, release)
            db.flush()

            from app.models.project import Project

            for project in db.execute(select(Project)).scalars():
                forecast_service.refresh_project_forecast(db, project)
            db.commit()

        print(f"Releases: {len(releases)}")
        print(f"  dispatch date preserved from planned_end : {moved_dispatch}")
        print(f"  commitment set from Mfg. Release target   : {set_commitment}")
        print(f"  left without a committed handover date    : {no_handover}")
        if args.apply:
            print(f"  baselines stamped                         : {stamped}")
            forecast = sum(1 for r in releases if r.forecast_end)
            print(f"  releases now carrying a forecast          : {forecast}")
        else:
            print()
            print("Dry run. Nothing was changed. Re-run with --apply.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
