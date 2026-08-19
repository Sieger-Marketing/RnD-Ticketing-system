"""Load the design team's release standards and the shared task template.

Two things are created:

* one published template holding the five tasks every design release runs --
  Concept, 3D Drawing, 2D Drawing, 2D Checking, Check Sheet Filling;
* the DSQ list for each product, so choosing a product on a new project
  produces its releases rather than someone typing them from memory.

Re-runnable. The standards are replaced wholesale on each run because they are
a definition rather than transactional data: if the design team revises the
Tower DSQ list, the new list is the truth and the old rows should not linger.
Projects already created keep the releases they were given -- those are real
work, and nothing here touches them.
"""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import Product, ProductFamily
from app.models.standard import ReleaseStandard
from app.models.template import DesignTemplate, DesignTemplateVersion, TemplateTask
from app.services import code_service

FIXTURE = Path(__file__).parent / "data" / "release_standards.json"

TEMPLATE_NAME = "Standard Design Release"
RELEASE_TYPE = "Design Release"

#: Checking cannot precede the drawing it checks, and the check sheet records
#: the outcome of that check. The three upstream tasks overlap in practice --
#: a 2D drawing often begins while the 3D model is still being finished.
GATING_TASKS = {"2D Checking", "Check Sheet Filling"}


def _family(db: Session) -> ProductFamily:
    family = db.execute(
        select(ProductFamily).where(ProductFamily.name == "Sieger Systems")
    ).scalar_one_or_none()
    if family is None:
        family = ProductFamily(
            code=code_service.next_code(db, "product_family"),
            name="Sieger Systems",
            description="Parking and storage systems Sieger designs.",
        )
        db.add(family)
        db.flush()
    return family


def _product(db: Session, name: str, aliases: list[str], family: ProductFamily) -> Product:
    """Find the product by name or any alias, else create it."""
    for candidate in [name, *aliases]:
        product = db.execute(
            select(Product).where(Product.name == candidate)
        ).scalar_one_or_none()
        if product:
            return product

    product = Product(
        code=code_service.next_code(db, "product"),
        name=name,
        product_family_id=family.id,
        description=f"{name} system.",
    )
    db.add(product)
    db.flush()
    return product


def _task_template(db: Session, tasks: list[str], family: ProductFamily) -> DesignTemplateVersion:
    template = db.execute(
        select(DesignTemplate).where(DesignTemplate.name == TEMPLATE_NAME)
    ).scalar_one_or_none()

    if template is not None:
        version = db.execute(
            select(DesignTemplateVersion)
            .where(
                DesignTemplateVersion.template_id == template.id,
                DesignTemplateVersion.is_published.is_(True),
            )
            .order_by(DesignTemplateVersion.version_number.desc())
        ).scalars().first()
        if version:
            return version
    else:
        template = DesignTemplate(
            code=code_service.next_code(db, "template"),
            name=TEMPLATE_NAME,
            release_type=RELEASE_TYPE,
            product_family_id=family.id,
            description=(
                "The five tasks every design release runs, whatever the product."
            ),
        )
        db.add(template)
        db.flush()

    version = DesignTemplateVersion(
        template_id=template.id, version_number=1, is_published=True
    )
    db.add(version)
    db.flush()

    for index, name in enumerate(tasks, start=1):
        db.add(
            TemplateTask(
                version_id=version.id,
                sequence=index,
                name=name,
                task_type=name,
                default_estimated_hours=0,
                complexity=3,
                is_mandatory=True,
                requires_review=name in GATING_TASKS,
                depends_on_sequence=index - 1 if index > 1 else None,
                depends_on_blocking=name in GATING_TASKS,
            )
        )
    db.flush()
    template.current_version_id = version.id
    db.flush()
    return version


def run(db: Session) -> dict:
    if not FIXTURE.exists():
        return {"skipped": "no fixture"}

    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    family = _family(db)
    version = _task_template(db, data["tasks"], family)

    products_touched = 0
    rows_written = 0

    for entry in data["products"]:
        product = _product(db, entry["product"], entry.get("aliases", []), family)
        products_touched += 1

        # A standard is a definition: replace it rather than accumulating
        # versions of it. Projects already created are untouched.
        for existing in db.execute(
            select(ReleaseStandard).where(ReleaseStandard.product_id == product.id)
        ).scalars().all():
            db.delete(existing)
        db.flush()

        for index, release in enumerate(entry["releases"], start=1):
            db.add(
                ReleaseStandard(
                    product_id=product.id,
                    variant="standard",
                    sequence=index,
                    name=release["name"],
                    is_default=release.get("default", True),
                    condition=release.get("condition"),
                    alternative_name=release.get("alternative"),
                )
            )
            rows_written += 1

        for variant in entry.get("variants", []):
            for index, release in enumerate(variant["releases"], start=1):
                db.add(
                    ReleaseStandard(
                        product_id=product.id,
                        variant=variant["name"],
                        variant_condition=variant.get("condition"),
                        sequence=index,
                        name=release["name"],
                        is_default=release.get("default", True),
                        condition=release.get("condition"),
                        alternative_name=release.get("alternative"),
                    )
                )
                rows_written += 1

    db.flush()
    return {
        "task_template": f"{TEMPLATE_NAME} v{version.version_number}",
        "tasks": len(data["tasks"]),
        "products": products_touched,
        "release_standards": rows_written,
    }
