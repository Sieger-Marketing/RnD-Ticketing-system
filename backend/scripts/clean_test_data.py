"""Remove the debris a test run leaves behind.

The suite creates projects, releases, tasks and people and deletes none of
them, because against a scratch database that is the cheapest thing that works.
Against the department's real database it is fabricated work: projects nobody
scoped, hours nobody logged. This removes it.

Safe by default: prints what it would delete and changes nothing. Pass --apply
to commit. Take a backup first --

    pg_dump -U designops -h 127.0.0.1 -d designops -F c -f backup.dump

Matching is by the exact names the fixtures use, never by a loose pattern, so a
real project called "Rules for Tower Foundation" is not swept up. Deleting a
project cascades to its releases, tasks, reviews, revisions and time entries;
deleting a test user cascades to their time entries and roles, and sets
authored records to null rather than removing them.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal  # noqa: E402

#: Names the test fixtures create, verbatim. LIKE patterns are anchored with a
#: trailing % only where the fixture appends a timestamp or a suffix.
PROJECT_PATTERNS = [
    "Acceptance Test - %",
    "RBAC probe - %",
    "Rules Test Project",
    "SCRATCH %",
    "Standard Test - %",
]

#: The factory in tests/conftest.py mints users as test.<label>.<stamp>@...
USER_PATTERN = "test.%@designops.dev"

COUNTED = [
    "projects",
    "design_releases",
    "tasks",
    "time_entries",
    "reviews",
    "revisions",
    "users",
]


def counts(db) -> dict[str, int]:
    return {t: db.execute(text(f"select count(*) from {t}")).scalar() or 0 for t in COUNTED}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually delete; without it nothing is written",
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        before = counts(db)

        doomed_projects = []
        for pattern in PROJECT_PATTERNS:
            rows = db.execute(
                text(
                    "select code, name,"
                    " (select count(*) from design_releases r where r.project_id = p.id),"
                    " (select count(*) from tasks t where t.project_id = p.id)"
                    " from projects p where name like :pattern order by code"
                ),
                {"pattern": pattern},
            ).all()
            doomed_projects.extend(rows)

        doomed_users = db.execute(
            text("select email from users where email like :pattern order by email"),
            {"pattern": USER_PATTERN},
        ).scalars().all()

        print(f"Database: {db.bind.url.database}")
        print()
        print(f"Projects to remove ({len(doomed_projects)}):")
        for code, name, releases, tasks in doomed_projects:
            print(f"   {code}  {name:44} releases={releases} tasks={tasks}")
        print()
        print(f"Test users to remove ({len(doomed_users)}):")
        for email in doomed_users:
            print(f"   {email}")
        print()

        survivors = db.execute(
            text("select code, name from projects order by code")
        ).all()
        doomed_codes = {code for code, _, _, _ in doomed_projects}
        print("Projects that will remain:")
        for code, name in survivors:
            if code not in doomed_codes:
                print(f"   {code}  {name}")
        print()

        if not args.apply:
            print("Dry run. Nothing was changed. Re-run with --apply to delete.")
            return 0

        removed = 0
        for pattern in PROJECT_PATTERNS:
            removed += db.execute(
                text("delete from projects where name like :pattern"),
                {"pattern": pattern},
            ).rowcount
        users_removed = db.execute(
            text("delete from users where email like :pattern"),
            {"pattern": USER_PATTERN},
        ).rowcount

        after = counts(db)
        db.commit()

        print(f"Deleted {removed} projects and {users_removed} users.")
        print()
        print(f"{'table':18} {'before':>8} {'after':>8}")
        for table in COUNTED:
            print(f"{table:18} {before[table]:>8} {after[table]:>8}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
