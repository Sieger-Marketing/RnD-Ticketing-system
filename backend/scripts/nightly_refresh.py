"""Bring the stored delay days and RAG ratings up to today's date.

Health and delay are computed against today, but they are stored on the row so
lists can filter and sort on them. Nothing about a release changes when it
slips past its committed date overnight, so the roll-up -- which runs only when
somebody touches the work -- never revisits it, and the release keeps showing
yesterday's colour. Left alone this drifts steadily: 92 releases were sitting
green with their handover date already behind them.

Run once a night, before anyone opens a dashboard. Idempotent.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

# The database URL is read from a .env resolved against the working directory,
# so a scheduled run that starts anywhere else finds no configuration and dies
# on a connection error that says nothing about the real cause. The task sets
# its working directory, but a script that only works from one place is a
# script that breaks the first time somebody runs it by hand.
os.chdir(BACKEND)

from app.db.session import SessionLocal  # noqa: E402
from app.services import health_service, time_service  # noqa: E402


def main() -> int:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with SessionLocal() as db:
        # Before the ratings, because a timer left running overnight is still
        # counting and its hours feed the effort figures the ratings read.
        closed = time_service.close_stale_timers(db)
        counts = health_service.sweep_delays(db)
        db.commit()

    print(
        f"[{stamp}] delay days updated: "
        f"{counts['tasks']} task(s), {counts['releases']} release(s), "
        f"{counts['projects']} project(s); "
        f"re-rated {counts['releases_rerated']} release(s) and "
        f"{counts['projects_rerated']} project(s)"
    )
    if closed:
        print(
            f"[{stamp}] closed {len(closed)} timer(s) left running overnight: "
            + ", ".join(f"{e.code} {e.hours}h" for e in closed)
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
