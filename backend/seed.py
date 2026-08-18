"""Seed the database.

    python seed.py              bootstrap only (permissions, roles, settings)
    python seed.py --demo       bootstrap plus the demonstration department
    python seed.py --demo --reset   wipe business data first, then reseed

`--reset` truncates the business tables but leaves the schema in place, so it
is a fast way to get back to a known demo state without re-running migrations.
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import text

from app.core.config import settings
from app.db.session import SessionLocal, engine
from app.seed import bootstrap, demo

#: Order matters only for readability -- TRUNCATE ... CASCADE handles the rest.
BUSINESS_TABLES = [
    "time_entries",
    "reviews",
    "revisions",
    "task_estimate_history",
    "task_dependencies",
    "tasks",
    "design_releases",
    "project_members",
    "projects",
    "template_tasks",
    "design_template_versions",
    "design_templates",
    "attachments",
    "comments",
    "notifications",
    "status_history",
    "audit_logs",
    "integration_records",
    "sync_logs",
    "user_skills",
    "user_capacity",
    "leave_records",
    "holidays",
    "skills",
    "products",
    "product_families",
    "customers",
    "user_roles",
    "users",
    "document_counters",
]


def reset(confirm: bool) -> None:
    if not confirm:
        print("Refusing to reset without --yes.")
        sys.exit(1)
    with engine.begin() as connection:
        connection.execute(
            text(f"TRUNCATE {', '.join(BUSINESS_TABLES)} RESTART IDENTITY CASCADE")
        )
    print(f"Reset {len(BUSINESS_TABLES)} tables.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the Design Operations database.")
    parser.add_argument("--demo", action="store_true", help="also seed demo data")
    parser.add_argument("--reset", action="store_true", help="wipe business data first")
    parser.add_argument("--yes", action="store_true", help="confirm a destructive reset")
    args = parser.parse_args()

    print(f"Database: {settings.DATABASE_URL.rsplit('@', 1)[-1]}")

    if args.reset:
        reset(args.yes)

    with SessionLocal() as db:
        result = bootstrap.run(db)
        db.commit()
        print("Bootstrap:", result)

        if args.demo:
            stats = demo.run(db, password=settings.SEED_DEFAULT_PASSWORD)
            db.commit()
            print("Demo data:", stats)
            if "skipped" not in stats:
                print(
                    f"\nSign in with any seeded account, password: "
                    f"{settings.SEED_DEFAULT_PASSWORD}\n"
                    "  Director        rajesh.varma@designops.dev\n"
                    "  Design Manager  lakshmi.subramanian@designops.dev\n"
                    "  Team Lead       suresh.balan@designops.dev\n"
                    "  Designer        arun.prakash@designops.dev"
                )


if __name__ == "__main__":
    main()
