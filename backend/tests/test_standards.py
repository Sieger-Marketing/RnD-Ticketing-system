"""The standard design releases per product, and applying them to a project.

The design team's list is the thing being protected here: a Puzzle releases
four DSQs with a fifth that depends on the level count, a Stacker releases
three unless the system is small. If applying a standard silently produced the
wrong number of releases, nobody would notice until the drawings were due.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest


@pytest.fixture(scope="module")
def puzzle(manager):
    products = manager.get("/api/products").json()
    product = next((p for p in products if p["name"] == "Puzzle"), None)
    if product is None:
        pytest.skip("the Puzzle standard has not been seeded on this database")
    return product


@pytest.fixture(scope="module")
def project(manager, puzzle):
    """A project of the right product, with no releases on it."""
    customers = manager.get("/api/customers").json()["items"]
    assert customers, "seed data is required for this test"
    today = date.today()
    response = manager.post(
        "/api/projects",
        json={
            "name": "Standard Test - Puzzle Stack",
            "customer_id": customers[0]["id"],
            "product_id": puzzle["id"],
            "project_type": "New Design",
            "priority": "Medium",
            "start_date": today.isoformat(),
            "required_completion_date": (today + timedelta(days=45)).isoformat(),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_the_catalogue_lists_every_product_that_has_a_standard(manager):
    response = manager.get("/api/release-standards")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body, "no product has a standard defined"

    for product in body:
        assert product["variants"], f"{product['product_name']} has an empty standard"
        for variant in product["variants"]:
            sequences = [r["sequence"] for r in variant["releases"]]
            assert sequences == sorted(sequences), "releases are out of design order"


def test_a_designer_can_read_the_standard(designer, puzzle):
    """It is reference material, not an admin screen."""
    response = designer.get(f"/api/products/{puzzle['id']}/release-standard")
    assert response.status_code == 200, response.text
    assert response.json()["variants"]


def test_every_release_runs_the_same_five_tasks(manager, puzzle):
    body = manager.get(f"/api/products/{puzzle['id']}/release-standard").json()
    assert body["tasks"] == [
        "Concept",
        "3D Drawing",
        "2D Drawing",
        "2D Checking",
        "Check Sheet Filling",
    ]


def test_a_conditional_release_is_offered_rather_than_assumed(manager, puzzle):
    """Foundation and Ceiling Supports depend on the level count."""
    body = manager.get(f"/api/products/{puzzle['id']}/release-standard").json()
    releases = body["variants"][0]["releases"]

    conditional = [r for r in releases if not r["is_default"]]
    assert conditional, "the Puzzle standard has lost its conditional releases"
    for release in conditional:
        assert release["condition"], f"{release['name']} is optional with no rule shown"


def test_applying_the_standard_creates_the_releases_with_their_tasks(
    manager, puzzle, project
):
    body = manager.get(f"/api/products/{puzzle['id']}/release-standard").json()
    releases = body["variants"][0]["releases"]
    defaults = [r["id"] for r in releases if r["is_default"]]

    response = manager.post(
        f"/api/projects/{project['id']}/apply-standard",
        json={"variant": "standard", "release_ids": defaults},
    )
    assert response.status_code == 201, response.text
    created = response.json()

    assert len(created) == len(defaults)
    assert [r["sequence_number"] for r in created] == list(range(1, len(defaults) + 1))
    for release in created:
        assert release["task_count"] == 5, f"{release['name']} did not get its tasks"

    names = manager.get(
        f"/api/releases/{created[0]['id']}/tasks"
    ).json()
    assert [t["name"] for t in names] == [
        "Concept",
        "3D Drawing",
        "2D Drawing",
        "2D Checking",
        "Check Sheet Filling",
    ]


def test_applying_the_same_standard_twice_does_not_duplicate_releases(
    manager, puzzle, project
):
    """A second click must not double a project's release list."""
    body = manager.get(f"/api/products/{puzzle['id']}/release-standard").json()
    defaults = [r["id"] for r in body["variants"][0]["releases"] if r["is_default"]]

    before = manager.get(
        "/api/releases", params={"project_id": project["id"], "page_size": 100}
    ).json()["total"]

    response = manager.post(
        f"/api/projects/{project['id']}/apply-standard",
        json={"variant": "standard", "release_ids": defaults},
    )
    assert response.status_code == 422, response.text

    after = manager.get(
        "/api/releases", params={"project_id": project["id"], "page_size": 100}
    ).json()["total"]
    assert after == before


def test_a_conditional_release_can_be_added_later(manager, puzzle, project):
    """The manager learns the site is a 2-level Puzzle after work has started."""
    body = manager.get(f"/api/products/{puzzle['id']}/release-standard").json()
    releases = body["variants"][0]["releases"]
    ceiling = next(r for r in releases if r["name"] == "Ceiling Supports")

    response = manager.post(
        f"/api/projects/{project['id']}/apply-standard",
        json={"variant": "standard", "release_ids": [ceiling["id"]]},
    )
    assert response.status_code == 201, response.text
    created = response.json()
    assert len(created) == 1
    assert created[0]["name"] == "Ceiling Supports"
    # Numbering continues after the releases already there.
    assert created[0]["sequence_number"] > 1


def test_a_release_from_another_product_is_refused(manager, project):
    """A Rotary release must not land on a Puzzle project."""
    catalogue = manager.get("/api/release-standards").json()
    other = next(
        (p for p in catalogue if p["product_name"] != "Puzzle"),
        None,
    )
    if other is None:
        pytest.skip("only one product has a standard on this database")

    alien = other["variants"][0]["releases"][0]["id"]
    response = manager.post(
        f"/api/projects/{project['id']}/apply-standard",
        json={"variant": "standard", "release_ids": [alien]},
    )
    assert response.status_code == 422, response.text
    assert "standard" in response.json()["error"]["message"].lower()


def test_a_designer_cannot_apply_a_standard(designer, project, puzzle):
    """Reading the standard is open; creating releases from it is not."""
    body = designer.get(f"/api/products/{puzzle['id']}/release-standard").json()
    any_release = body["variants"][0]["releases"][0]["id"]

    response = designer.post(
        f"/api/projects/{project['id']}/apply-standard",
        json={"variant": "standard", "release_ids": [any_release]},
    )
    assert response.status_code == 403, response.text


def test_a_product_with_two_standards_keeps_them_separate(manager):
    """A Stacker releases 3 DSQs, or 1 when the system is 10 units or fewer."""
    catalogue = manager.get("/api/release-standards").json()
    stacker = next(
        (p for p in catalogue if len(p["variants"]) > 1),
        None,
    )
    if stacker is None:
        pytest.skip("no product on this database defines a variant standard")

    named = [v for v in stacker["variants"] if v["variant"] != "standard"]
    assert named, "the alternative set lost its name"
    for variant in named:
        assert variant["condition"], "an alternative standard with no rule is unusable"
        assert variant["releases"], "an alternative standard with no releases"
