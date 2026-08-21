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

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal  # noqa: E402
from app.services import health_service  # noqa: E402


def main() -> int:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with SessionLocal() as db:
        counts = health_service.sweep_delays(db)
        db.commit()

    print(
        f"[{stamp}] delay days updated: "
        f"{counts['tasks']} task(s), {counts['releases']} release(s), "
        f"{counts['projects']} project(s); "
        f"re-rated {counts['releases_rerated']} release(s) and "
        f"{counts['projects_rerated']} project(s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
