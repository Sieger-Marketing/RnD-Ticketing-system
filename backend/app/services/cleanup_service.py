"""Finding and removing the fiction, wherever the database happens to live.

Two kinds accumulate before a system goes live: the demo seed invents a
department so the screens have something to show, and the test suite invents
more on every run. Both stop being useful the day real people sign in, at which
point they are indistinguishable from real work to anyone reading a project
list.

This is the shared implementation. The command-line script and the
administrator endpoint both call it, so the two cannot disagree about what
counts as fiction -- and the endpoint exists because a managed host may not
give you a shell, which is precisely when a database full of demo data is
hardest to do anything about.

Identification is by the fixtures themselves, never by a loose pattern: the
exact customer codes the seed writes, the address domain it mints, the verbatim
project names the tests use. A real customer named Meridian, or a project
called "Test rig for Tower", is not swept up.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.catalog import Customer
from app.models.project import Project
from app.models.user import User
from app.seed.demo import CUSTOMERS as DEMO_CUSTOMERS

#: Exactly the codes app/seed/demo.py writes.
DEMO_CUSTOMER_CODES = [code for _, code, _, _ in DEMO_CUSTOMERS]

#: The address domain every invented person is minted under -- by the demo seed
#: and by the test fixtures alike. Real staff are on the company domain. An
#: employee code is deliberately not treated as proof of a real person: the auth
#: tests mint accounts carrying codes like SIESTEST3F2A.
DEMO_EMAIL_SUFFIX = "@designops.dev"

#: Verbatim names the test fixtures create.
TEST_PROJECT_PATTERNS = [
    "Acceptance Test - %",
    "RBAC probe - %",
    "Rules Test Project",
    "SCRATCH %",
    "Standard Test - %",
]

#: Throwaway names a person types while trying the system out. Matched exactly
#: and case-insensitively, never as a prefix: "TEST" goes, "Test rig for Tower"
#: stays, because the second one is somebody's actual project.
THROWAWAY_NAMES = ["test", "testing", "demo", "sample", "dummy", "asdf", "abc"]


@dataclass(slots=True)
class Found:
    """What would be removed, described well enough to be read before agreeing."""

    projects: list[Project] = field(default_factory=list)
    customers: list[Customer] = field(default_factory=list)
    users: list[User] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (self.projects or self.customers or self.users)

    def as_dict(self) -> dict:
        return {
            "projects": [
                {"code": p.code, "name": p.name} for p in self.projects
            ],
            "customers": [
                {"code": c.customer_code, "name": c.name} for c in self.customers
            ],
            "users": [
                {"email": u.email, "full_name": u.full_name} for u in self.users
            ],
        }


def find(db: Session, *, extra_codes: list[str] | None = None) -> Found:
    """Everything this considers fiction. Reads only."""
    demo_customers = db.execute(
        select(Customer).where(Customer.customer_code.in_(DEMO_CUSTOMER_CODES))
    ).scalars().all()

    conditions = [Project.name.like(pattern) for pattern in TEST_PROJECT_PATTERNS]
    conditions.append(func.lower(func.trim(Project.name)).in_(THROWAWAY_NAMES))
    if demo_customers:
        conditions.append(Project.customer_id.in_([c.id for c in demo_customers]))
    if extra_codes:
        conditions.append(
            Project.code.in_([code.strip().upper() for code in extra_codes if code.strip()])
        )

    projects = db.execute(
        select(Project).where(or_(*conditions)).order_by(Project.code)
    ).scalars().all()

    # The administrator is protected unconditionally: whatever else this gets
    # wrong, it must not be the thing that locks the operator out.
    users = db.execute(
        select(User)
        .where(
            User.email.like(f"%{DEMO_EMAIL_SUFFIX}"),
            User.email != settings.ADMIN_EMAIL,
        )
        .order_by(User.email)
    ).scalars().all()

    return Found(projects=list(projects), customers=list(demo_customers), users=list(users))


def survivors(db: Session, found: Found) -> dict:
    """What is left standing, so the caller can check before agreeing."""
    doomed_projects = {p.id for p in found.projects}
    doomed_users = {u.id for u in found.users}

    return {
        "projects": [
            {"code": p.code, "name": p.name}
            for p in db.execute(select(Project).order_by(Project.code)).scalars()
            if p.id not in doomed_projects
        ],
        "users": [
            {"employee_code": u.employee_code, "full_name": u.full_name}
            for u in db.execute(select(User).order_by(User.employee_code)).scalars()
            if u.id not in doomed_users
        ],
    }


def purge(db: Session, found: Found) -> dict:
    """Remove what `find` identified. Deleting a project cascades to its
    releases, tasks, reviews, revisions and time entries.

    Projects go before customers: a project points at a customer and the key is
    set null rather than cascading, so removing customers first would leave a
    surviving project pointing at nothing.
    """
    removed = {
        "projects": len(found.projects),
        "customers": len(found.customers),
        "users": len(found.users),
    }

    for project in found.projects:
        db.delete(project)
    db.flush()
    for user in found.users:
        db.delete(user)
    db.flush()
    for customer in found.customers:
        db.delete(customer)
    db.flush()

    return removed
