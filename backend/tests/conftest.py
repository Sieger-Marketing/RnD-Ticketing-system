"""Test fixtures.

Tests run against a real Postgres database and the real HTTP stack, because
the things worth proving here -- the workflow state machine, the permission
gates, the KPI roll-ups -- are exactly the things a mocked session would stop
testing. Each test creates its own project and cleans up nothing, so runs are
additive.

That additive habit is safe against a scratch database and ruinous against a
live one: a full run leaves behind projects, users and time entries, which in a
department's real database is fabricated work nobody did. So the target is
chosen and checked *before* the application is imported, and a database that is
not demonstrably a test database is refused rather than written to.
"""

from __future__ import annotations

import os
import pathlib
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

# Redirect before importing anything that reads settings: pydantic-settings
# resolves DATABASE_URL at import time, and an environment variable outranks
# the .env file.
_TEST_URL = os.environ.get("TEST_DATABASE_URL")
if _TEST_URL:
    os.environ["DATABASE_URL"] = _TEST_URL

from app.core.config import settings  # noqa: E402


def _target_database() -> str:
    return settings.DATABASE_URL.rsplit("/", 1)[-1].split("?")[0]


def _refuse_unless_scratch() -> None:
    """Stop the suite reaching a database that holds real work."""
    name = _target_database()
    if name.endswith("_test") or name.endswith("_scratch"):
        return
    if os.environ.get("DESIGNOPS_TESTS_MAY_WRITE_HERE") == "1":
        return
    raise RuntimeError(
        f"Refusing to run the test suite against database {name!r}.\n"
        "The suite writes projects, users and time entries and deletes none of "
        "them, so pointing it at a live database fabricates work that nobody "
        "did.\n"
        "Give it a scratch database instead:\n"
        "  set TEST_DATABASE_URL=postgresql+psycopg://"
        "designops:PASSWORD@127.0.0.1:5432/designops_test\n"
        "If you genuinely mean to write here, set "
        "DESIGNOPS_TESTS_MAY_WRITE_HERE=1."
    )


_refuse_unless_scratch()
from app.db.session import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import bootstrap, demo, standards  # noqa: E402

DIRECTOR = "rajesh.varma@designops.dev"
MANAGER = "lakshmi.subramanian@designops.dev"
LEAD = "suresh.balan@designops.dev"
DESIGNER = "arun.prakash@designops.dev"


@pytest.fixture(scope="session", autouse=True)
def _ensure_bootstrap():
    """Bring a scratch database up to schema, then seed what tests assume.

    A fresh scratch database has no tables at all, so the migrations run first;
    on an already-migrated one this is a no-op that costs a fraction of a
    second.
    """
    from alembic import command
    from alembic.config import Config

    config = Config(str(pathlib.Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
    command.upgrade(config, "head")

    with SessionLocal() as db:
        bootstrap.run(db)
        db.commit()
        # The suite signs in as the demo department's people, so they have to
        # exist with the password the fixtures use.
        demo.run(db, password=settings.SEED_DEFAULT_PASSWORD)
        db.commit()
        # The standards tests read the per-product release lists; without this
        # they would skip rather than fail, and quietly stop protecting them.
        standards.run(db)
        db.commit()


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(scope="session")
def db():
    session = SessionLocal()
    yield session
    session.close()


class Actor:
    """A signed-in user, with its bearer token pre-attached."""

    def __init__(self, client: TestClient, email: str, password: str) -> None:
        response = client.post(
            "/api/auth/login", json={"email": email, "password": password}
        )
        assert response.status_code == 200, response.text
        body = response.json()
        self.client = client
        self.token = body["access_token"]
        self.user = body["user"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    @property
    def id(self) -> str:
        return self.user["id"]

    def get(self, url, **kwargs):
        return self.client.get(url, headers=self.headers, **kwargs)

    def post(self, url, **kwargs):
        return self.client.post(url, headers=self.headers, **kwargs)

    def patch(self, url, **kwargs):
        return self.client.patch(url, headers=self.headers, **kwargs)

    def put(self, url, **kwargs):
        return self.client.put(url, headers=self.headers, **kwargs)

    def delete(self, url, **kwargs):
        return self.client.delete(url, headers=self.headers, **kwargs)


def _actor(client: TestClient, email: str) -> Actor:
    return Actor(client, email, settings.SEED_DEFAULT_PASSWORD)


@pytest.fixture(scope="session")
def director(client) -> Actor:
    return _actor(client, DIRECTOR)


@pytest.fixture(scope="session")
def manager(client) -> Actor:
    return _actor(client, MANAGER)


@pytest.fixture(scope="session")
def lead(client) -> Actor:
    return _actor(client, LEAD)


@pytest.fixture(scope="session")
def designer(client) -> Actor:
    return _actor(client, DESIGNER)


@pytest.fixture(scope="session")
def make_designer(client, manager, lead):
    """Factory for a brand-new designer, unique to this test run.

    Tests that log time need an empty timesheet: the time service rejects
    overlapping entries, so re-running the suite against the same database
    would otherwise collide with the previous run's entries. Creating a fresh
    person per run keeps the suite repeatable without wiping the database.
    """
    created: list[Actor] = []

    def _make(label: str) -> Actor:
        stamp = datetime.now(UTC).strftime("%y%m%d%H%M%S%f")
        email = f"test.{label}.{stamp}@designops.dev"
        password = "TestUser@12345"
        response = manager.post(
            "/api/users",
            json={
                "email": email,
                "password": password,
                "full_name": f"Test {label.title()} {stamp[-6:]}",
                "designation": "Design Engineer",
                "department": "Design",
                "roles": ["Designer"],
                "reports_to_id": lead.id,
                "standard_daily_hours": 8,
            },
        )
        assert response.status_code == 201, response.text
        actor = Actor(client, email, password)
        created.append(actor)
        return actor

    return _make
