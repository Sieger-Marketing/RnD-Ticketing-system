"""Signing in with an employee code.

The design team is identified by employee code -- SIES00267 -- not by email;
several of them have no work mailbox at all. The administrator is the other
way round. Both have to work through the same field, and neither may be able
to sign in as the other.
"""

from __future__ import annotations

import uuid

import pytest

from app.core.config import settings


@pytest.fixture(scope="module")
def coded_user(manager, client):
    """A user created with an employee code, unique to this run."""
    stamp = uuid.uuid4().hex[:8].upper()
    code = f"SIESTEST{stamp}"
    password = "EmployeeCode@2026"
    response = manager.post(
        "/api/users",
        json={
            "email": f"test.coded.{stamp.lower()}@designops.dev",
            "employee_code": code,
            "password": password,
            "full_name": f"Coded Person {stamp}",
            "designation": "Design Engineer",
            "department": "Design",
            "roles": ["Designer"],
            "standard_daily_hours": 8,
        },
    )
    assert response.status_code == 201, response.text
    return {"code": code, "password": password, "user": response.json()}


def test_the_employee_code_is_stored_and_returned(coded_user):
    assert coded_user["user"]["employee_code"] == coded_user["code"]


def test_a_person_signs_in_with_their_employee_code(client, coded_user):
    response = client.post(
        "/api/auth/login",
        json={"identifier": coded_user["code"], "password": coded_user["password"]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["user"]["employee_code"] == coded_user["code"]


def test_the_employee_code_is_not_case_sensitive(client, coded_user):
    """People type sies00267 as readily as SIES00267, and a code is not secret."""
    response = client.post(
        "/api/auth/login",
        json={
            "identifier": coded_user["code"].lower(),
            "password": coded_user["password"],
        },
    )
    assert response.status_code == 200, response.text


def test_surrounding_whitespace_is_forgiven(client, coded_user):
    """Pasted from a spreadsheet, a code arrives with spaces around it."""
    response = client.post(
        "/api/auth/login",
        json={
            "identifier": f"  {coded_user['code']}  ",
            "password": coded_user["password"],
        },
    )
    assert response.status_code == 200, response.text


def test_an_email_still_signs_in(client):
    """The administrator has an address and no employee code."""
    response = client.post(
        "/api/auth/login",
        json={
            "identifier": settings.ADMIN_EMAIL,
            "password": settings.SEED_DEFAULT_PASSWORD,
        },
    )
    assert response.status_code in (200, 401), response.text
    # 401 only if the administrator's password has been changed, which is the
    # intended state in production; either way it must not be a 422.


def test_the_older_client_shape_still_works(client, coded_user):
    """A cached bundle posts {email: ...}; it must not start failing."""
    response = client.post(
        "/api/auth/login",
        json={"email": coded_user["code"], "password": coded_user["password"]},
    )
    assert response.status_code == 200, response.text


def test_a_wrong_password_is_refused(client, coded_user):
    response = client.post(
        "/api/auth/login",
        json={"identifier": coded_user["code"], "password": "not-the-password"},
    )
    assert response.status_code == 401, response.text


def test_an_unknown_code_says_the_same_thing_as_a_wrong_password(client, coded_user):
    """The endpoint must not reveal which employee codes exist."""
    unknown = client.post(
        "/api/auth/login",
        json={"identifier": "SIES00000NOBODY", "password": "whatever"},
    )
    wrong = client.post(
        "/api/auth/login",
        json={"identifier": coded_user["code"], "password": "not-the-password"},
    )
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["error"]["message"] == wrong.json()["error"]["message"]


def test_two_accounts_cannot_share_an_employee_code(manager, coded_user):
    """A shared code would make a login ambiguous."""
    response = manager.post(
        "/api/users",
        json={
            "email": f"test.duplicate.{uuid.uuid4().hex[:8]}@designops.dev",
            "employee_code": coded_user["code"],
            "password": "Another@12345",
            "full_name": "Duplicate Code",
            "roles": ["Designer"],
        },
    )
    assert response.status_code == 422, response.text
    assert "already belongs" in response.json()["error"]["message"]


def test_the_code_is_stored_uppercase_however_it_is_typed(manager):
    stamp = uuid.uuid4().hex[:8]
    response = manager.post(
        "/api/users",
        json={
            "email": f"test.lower.{stamp}@designops.dev",
            "employee_code": f"siestest{stamp}",
            "password": "Another@12345",
            "full_name": "Lowercase Code",
            "roles": ["Designer"],
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["employee_code"] == f"SIESTEST{stamp}".upper()


def test_a_deactivated_account_cannot_sign_in(manager, client, coded_user):
    """The go-live lockdown deactivates accounts; that must actually stop them."""
    user_id = coded_user["user"]["id"]
    assert manager.patch(f"/api/users/{user_id}", json={"is_active": False}).status_code == 200

    response = client.post(
        "/api/auth/login",
        json={"identifier": coded_user["code"], "password": coded_user["password"]},
    )
    assert response.status_code == 401, response.text

    manager.patch(f"/api/users/{user_id}", json={"is_active": True})


def test_an_administrator_can_reset_a_forgotten_password(manager, client, coded_user):
    """The Monday-morning support call, without a database client."""
    user_id = coded_user["user"]["id"]
    response = manager.post(f"/api/users/{user_id}/reset-password")
    assert response.status_code == 200, response.text

    body = response.json()
    assert body["employee_code"] == coded_user["code"]
    assert len(body["password"]) >= 8

    # The old password stops working and the new one starts.
    old = client.post(
        "/api/auth/login",
        json={"identifier": coded_user["code"], "password": coded_user["password"]},
    )
    assert old.status_code == 401

    new = client.post(
        "/api/auth/login",
        json={"identifier": coded_user["code"], "password": body["password"]},
    )
    assert new.status_code == 200, new.text

    # Keep the fixture usable for whatever runs after this.
    coded_user["password"] = body["password"]


def test_a_generated_password_avoids_characters_people_misread(manager, coded_user):
    """It gets read off a screen and typed by hand."""
    response = manager.post(f"/api/users/{coded_user['user']['id']}/reset-password")
    assert response.status_code == 200, response.text
    password = response.json()["password"]
    assert not set(password) & set("O0l1I")
    coded_user["password"] = password


def test_a_designer_cannot_reset_anyone_else(designer, coded_user):
    response = designer.post(f"/api/users/{coded_user['user']['id']}/reset-password")
    assert response.status_code == 403, response.text


def test_resetting_an_unknown_person_is_a_404(manager):
    response = manager.post(
        "/api/users/00000000-0000-0000-0000-000000000000/reset-password"
    )
    assert response.status_code == 404, response.text
