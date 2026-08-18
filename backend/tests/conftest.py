"""Test fixtures.

Tests run against the real Postgres database and the real HTTP stack, because
the things worth proving here -- the workflow state machine, the permission
gates, the KPI roll-ups -- are exactly the things a mocked session would stop
testing. Each test creates its own project and cleans up nothing, so runs are
additive and never mutate the seeded demo department.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.session import SessionLocal
from app.main import app
from app.seed import bootstrap

DIRECTOR = "rajesh.varma@designops.dev"
MANAGER = "lakshmi.subramanian@designops.dev"
LEAD = "suresh.balan@designops.dev"
DESIGNER = "arun.prakash@designops.dev"


@pytest.fixture(scope="session", autouse=True)
def _ensure_bootstrap():
    with SessionLocal() as db:
        bootstrap.run(db)
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
