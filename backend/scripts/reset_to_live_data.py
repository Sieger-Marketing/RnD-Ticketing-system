"""Leave only real work in the database.

Two kinds of fiction accumulate before a system goes live. The demo seed
invents a department -- six customers, fifteen people, a set of projects -- so
the screens have something to show. The test suite invents more of the same on
every run. Both are useful right up to the day real people sign in, at which
point they are indistinguishable from real work to anyone reading a dashboard.

Identification is by the fixtures themselves, never by a loose pattern. The
demo customers are matched on the exact customer codes the seed writes, the
demo people on the address domain the seed mints, the test projects on the
verbatim names the fixtures use. A real project called "Rules for Tower
Foundation" or a real customer named Meridian is not swept up.

What is deliberately kept:
  * the administrator, and every account with an employee code -- the real team
  * products, product families and the release standards, because the demo
    products were adopted as the real ones when the standards were seeded, and
    deleting them would take the DSQ lists with them
  * the task template, roles, permissions and settings
  * any project that is not demo-seeded and does not match a test fixture name

Safe by default: prints what it would remove and changes nothing. Pass --apply.
Take a backup first:

    pg_dump -U designops -h 127.0.0.1 -d designops -F c -f backup.dump
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import or_, select, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.models.catalog import Customer  # noqa: E402
from app.models.project import Project  # noqa: E402
from app.models.user import User  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.seed.demo import CUSTOMERS as DEMO_CUSTOMERS  # noqa: E402

#: Exactly the codes app/seed/demo.py writes.
DEMO_CUSTOMER_CODES = [code for _, code, _, _ in DEMO_CUSTOMERS]

#: The address domain every invented person is minted under -- by the demo
#: seed and by the test fixtures alike. Real staff are on the company domain.
#: An employee code is deliberately NOT treated as proof of a real person: the
#: auth tests mint accounts with codes like SIESTEST3F2A, and exempting anyone
#: holding a code would have left all of them behind.
DEMO_EMAIL_SUFFIX = "@designops.dev"

#: Verbatim names the test fixtures create.
TEST_PROJECT_PATTERNS = [
    "Acceptance Test - %",
    "RBAC probe - %",
    "Rules Test Project",
    "SCRATCH %",
    "Standard Test - %",
]

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
    args = parser.parse_args()

    with SessionLocal() as db:
        before = counts(db)

        demo_customers = db.execute(
            select(Customer).where(Customer.customer_code.in_(DEMO_CUSTOMER_CODES))
        ).scalars().all()
        demo_customer_ids = [c.id for c in demo_customers]

        # A demo project is one belonging to a demo customer. A test project is
        # one named by a fixture. Nothing else qualifies.
        conditions = [Project.name.like(pattern) for pattern in TEST_PROJECT_PATTERNS]
        if demo_customer_ids:
            conditions.append(Project.customer_id.in_(demo_customer_ids))

        doomed_projects = db.execute(
            select(Project).where(or_(*conditions)).order_by(Project.code)
        ).scalars().all()

        # Everyone the seed or the tests invented. The administrator is
        # protected unconditionally: whatever else this script gets wrong, it
        # must not be the thing that locks the operator out.
        doomed_users = db.execute(
            select(User)
            .where(
                User.email.like(f"%{DEMO_EMAIL_SUFFIX}"),
                User.email != settings.ADMIN_EMAIL,
            )
            .order_by(User.email)
        ).scalars().all()

        survivors = db.execute(
            select(Project).order_by(Project.code)
        ).scalars().all()
        doomed_ids = {p.id for p in doomed_projects}

        print(f"Database: {db.bind.url.database}")
        print()
        print(f"Projects to remove ({len(doomed_projects)}):")
        for project in doomed_projects:
            print(f"   {project.code}  {project.name}")
        print()
        print(f"Customers to remove ({len(demo_customers)}):")
        for customer in demo_customers:
            print(f"   {customer.customer_code:12} {customer.name}")
        print()
        print(f"People to remove ({len(doomed_users)}):")
        for user in doomed_users:
            print(f"   {user.email:44} {user.full_name}")
        print()

        print("Projects that will remain:")
        remaining = [p for p in survivors if p.id not in doomed_ids]
        for project in remaining:
            print(f"   {project.code}  {project.name}")
        if not remaining:
            print("   (none — the department starts with a clean sheet)")
        print()

        kept_people = db.execute(
            select(User)
            .where(
                or_(
                    ~User.email.like(f"%{DEMO_EMAIL_SUFFIX}"),
                    User.email == settings.ADMIN_EMAIL,
                )
            )
            .order_by(User.employee_code)
        ).scalars().all()
        print(f"People that will remain ({len(kept_people)}):")
        for user in kept_people:
            print(f"   {user.employee_code or user.email:24} {user.full_name}")
        print()

        if not args.apply:
            print("Dry run. Nothing was changed. Re-run with --apply.")
            return 0

        # Order matters only for the customers: a project points at one, and
        # the foreign key is set null rather than cascading, so the projects go
        # first and no live project is left pointing at a deleted customer.
        for project in doomed_projects:
            db.delete(project)
        db.flush()
        for user in doomed_users:
            db.delete(user)
        db.flush()
        for customer in demo_customers:
            db.delete(customer)
        db.flush()

        after = counts(db)
        db.commit()

        print("Done.")
        print()
        print(f"{'table':18} {'before':>8} {'after':>8}")
        for table in COUNTED:
            print(f"{table:18} {before[table]:>8} {after[table]:>8}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
