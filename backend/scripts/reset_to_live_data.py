"""Leave only real work in the database.

A thin wrapper over app/services/cleanup_service.py, which is also what the
administrator endpoint calls, so the command line and the button cannot
disagree about what counts as fiction. The rules and the reasoning live there.

Safe by default: prints what it would remove and changes nothing. Pass --apply.
Take a backup first:

    pg_dump -U designops -h 127.0.0.1 -d designops -F c -f backup.dump
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal  # noqa: E402
from app.services import cleanup_service  # noqa: E402

COUNTED = [
    "projects",
    "design_releases",
    "tasks",
    "time_entries",
    "reviews",
    "revisions",
    "users",
    "customers",
]


def counts(db) -> dict[str, int]:
    return {t: db.execute(text(f"select count(*) from {t}")).scalar() or 0 for t in COUNTED}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="delete; without it nothing is written"
    )
    parser.add_argument(
        "--codes",
        default="",
        help="also remove these project codes, comma separated, e.g. PRJ-0012,PRJ-0013",
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        before = counts(db)
        found = cleanup_service.find(
            db, extra_codes=args.codes.split(",") if args.codes else None
        )
        remaining = cleanup_service.survivors(db, found)

        print(f"Database: {db.bind.url.database}")
        print()
        print(f"Projects to remove ({len(found.projects)}):")
        for project in found.projects:
            print(f"   {project.code}  {project.name}")
        print()
        print(f"Customers to remove ({len(found.customers)}):")
        for customer in found.customers:
            print(f"   {customer.customer_code:12} {customer.name}")
        print()
        print(f"People to remove ({len(found.users)}):")
        for user in found.users:
            print(f"   {user.email:44} {user.full_name}")
        print()

        print("Projects that will remain:")
        for project in remaining["projects"]:
            print(f"   {project['code']}  {project['name']}")
        if not remaining["projects"]:
            print("   (none - the department starts with a clean sheet)")
        print()
        print(f"People that will remain ({len(remaining['users'])}):")
        for user in remaining["users"]:
            print(f"   {user['employee_code'] or '-':24} {user['full_name']}")
        print()

        if not args.apply:
            print("Dry run. Nothing was changed. Re-run with --apply.")
            return 0

        removed = cleanup_service.purge(db, found)
        after = counts(db)
        db.commit()

        print(
            f"Removed {removed['projects']} project(s), "
            f"{removed['customers']} customer(s), {removed['users']} user(s)."
        )
        print()
        print(f"{'table':18} {'before':>8} {'after':>8}")
        for table in COUNTED:
            print(f"{table:18} {before[table]:>8} {after[table]:>8}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
