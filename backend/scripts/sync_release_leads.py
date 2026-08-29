"""Give every release the lead of the project it belongs to.

A release created without a lead belongs to nobody, and the consequence runs
downhill: its tasks inherit no lead either, and a review submitted against one
of those tasks routes to nobody at all. Thirty of thirty-one releases were in
that state while every project had a lead, so the information existed the whole
time -- it simply was not being carried down.

Fills blanks only. A release whose lead was deliberately set to somebody other
than the project's is a decision, not a gap, and this refuses to overwrite it.
Those are reported instead so the difference can be looked at rather than
silently removed.

Assigning cascades to the release's unrouted tasks, which is the point: it is
what gives a review somebody to go to.

Quiet by default. Filling in a field that should always have been set is one
decision about thirty releases, not thirty decisions, and thirty "Release
assigned" notices -- each copied to the design manager -- would bury the
notifications that report something happening now. Pass --notify to send them.

Safe by default: prints what it would change. Pass --apply.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from sqlalchemy import select

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

from app.db.session import SessionLocal  # noqa: E402
from app.models.project import Project  # noqa: E402
from app.models.release import DesignRelease  # noqa: E402
from app.models.task import Task  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services import release_service  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the changes")
    parser.add_argument(
        "--notify", action="store_true", help="tell each lead (off by default)"
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        actor = db.execute(
            select(User).where(User.email == "admin@sieger.in")
        ).scalar_one_or_none()

        filled: list[tuple[str, str, int]] = []
        no_project_lead: list[str] = []
        differing: list[tuple[str, str, str]] = []

        for release in db.execute(select(DesignRelease)).scalars():
            project = db.get(Project, release.project_id) if release.project_id else None
            lead_id = project.team_lead_id if project else None

            if release.team_lead_id is not None:
                if lead_id and release.team_lead_id != lead_id:
                    differing.append(
                        (
                            release.code,
                            _name(db, release.team_lead_id),
                            _name(db, lead_id),
                        )
                    )
                continue

            if lead_id is None:
                no_project_lead.append(release.code)
                continue

            orphan_tasks = db.execute(
                select(Task).where(
                    Task.release_id == release.id, Task.team_lead_id.is_(None)
                )
            ).scalars().all()

            if args.apply:
                lead = db.get(User, lead_id)
                release_service.assign_team_lead(
                    db, release, lead, actor=actor, notify=args.notify
                )
            filled.append((release.code, _name(db, lead_id), len(orphan_tasks)))

        if args.apply:
            db.commit()

        for code, lead, n_tasks in filled:
            tasks = f", and {n_tasks} task(s) with it" if n_tasks else ""
            print(f"  {code} -> {lead}{tasks}")
        for code in no_project_lead:
            print(f"  KEEP {code}: its project has no lead either")
        for code, on_release, on_project in differing:
            print(f"  KEEP {code}: set to {on_release}, project's is {on_project}")

        print()
        print(f"  filled            : {len(filled)}")
        print(f"  left, no project lead : {len(no_project_lead)}")
        print(f"  left, deliberately different : {len(differing)}")
        if not args.apply:
            print()
            print("Dry run. Nothing was changed. Re-run with --apply.")
        elif not args.notify and filled:
            print("  (nobody was notified; pass --notify if they should be)")
        return 0


def _name(db, user_id) -> str:
    user = db.get(User, user_id) if user_id else None
    return user.full_name if user else "nobody"


if __name__ == "__main__":
    raise SystemExit(main())
