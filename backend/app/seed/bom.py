"""Seed the imported BOM project from its fixture.

The design team's tracker lives in a spreadsheet on someone's machine, which
is no use to a deployed service. The parsed result is committed instead, so
the same project can be created on any environment without moving a file
around or handing a database password to anything.

Deliberately skip-if-present rather than replace-if-present. This runs inside
the deploy command, and a replace would wipe whatever the team had changed
since the last deploy -- their edits would vanish every time someone pushed.
Re-importing is therefore an explicit act, not a side effect of shipping.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import ProjectStatus, ReleaseStatus, TaskStatus
from app.models.catalog import Product, ProductFamily
from app.models.project import Project
from app.models.release import DesignRelease
from app.models.task import Task
from app.models.template import DesignTemplate, DesignTemplateVersion, TemplateTask
from app.models.user import User
from app.services import code_service, rollup_service

FIXTURE = Path(__file__).parent / "data" / "bom_project.json"

RELEASE_TYPE = "BOM Release"

#: The five phases in order, with the task type each one is.
PHASE_ORDER = [
    ("Concept", "Layout"),
    ("Long Lead & RM", "Coordination"),
    ("3D Design", "Modelling"),
    ("Mfg. Release", "Drawing"),
    ("Packing list & Stuffing", "Documentation"),
]

#: Phases whose input must exist first. Concept, procurement and modelling
#: genuinely overlap in practice; a drawing release cannot precede the model it
#: is taken from, and packing cannot precede the drawings.
GATING = {"Mfg. Release", "Packing list & Stuffing"}


def _as_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _template(db: Session, family_id) -> DesignTemplateVersion:
    template = db.execute(
        select(DesignTemplate).where(DesignTemplate.name == "BOM Release — Standard")
    ).scalar_one_or_none()

    if template is not None:
        published = db.execute(
            select(DesignTemplateVersion)
            .where(
                DesignTemplateVersion.template_id == template.id,
                DesignTemplateVersion.is_published.is_(True),
            )
            .order_by(DesignTemplateVersion.version_number.desc())
        ).scalars().first()
        if published:
            return published
    else:
        template = DesignTemplate(
            code=code_service.next_code(db, "template"),
            name="BOM Release — Standard",
            release_type=RELEASE_TYPE,
            product_family_id=family_id,
            description=(
                "The design team's five-phase BOM release: concept, long-lead "
                "procurement, 3D design, manufacturing release, then packing."
            ),
        )
        db.add(template)
        db.flush()

    version = DesignTemplateVersion(
        template_id=template.id, version_number=1, is_published=True
    )
    db.add(version)
    db.flush()

    for index, (name, task_type) in enumerate(PHASE_ORDER, start=1):
        db.add(
            TemplateTask(
                version_id=version.id,
                sequence=index,
                name=name,
                task_type=task_type,
                default_estimated_hours=0,
                complexity=3,
                is_mandatory=True,
                requires_review=name in GATING,
                depends_on_sequence=index - 1 if index > 1 else None,
                depends_on_blocking=name in GATING,
            )
        )
    db.flush()
    template.current_version_id = version.id
    db.flush()
    return version


def _product(db: Session, name: str) -> Product:
    product = db.execute(select(Product).where(Product.name == name)).scalar_one_or_none()
    if product:
        return product

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

    product = Product(
        code=code_service.next_code(db, "product"),
        name=name,
        product_family_id=family.id,
        description=f"{name} system.",
    )
    db.add(product)
    db.flush()
    return product


def run(db: Session, *, keep_demo_project: str | None = None) -> dict:
    """Create the imported project if it is not already there."""
    if not FIXTURE.exists():
        return {"skipped": "no fixture"}

    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    name = data["project"]

    if db.execute(select(Project).where(Project.name == name)).scalar_one_or_none():
        return {"skipped": f"{name} already present"}

    removed = 0
    if keep_demo_project:
        keeper = db.execute(
            select(Project).where(Project.name == keep_demo_project)
        ).scalar_one_or_none()
        for project in db.execute(select(Project)).scalars().all():
            if keeper and project.id == keeper.id:
                continue
            db.delete(project)
            removed += 1
        db.flush()

    manager = db.execute(
        select(User).where(User.email.like("lakshmi%"))
    ).scalars().first() or db.execute(select(User)).scalars().first()

    product = _product(db, data["product"])
    version = _template(db, product.product_family_id)

    assemblies = data["assemblies"]
    dispatches = [_as_date(a["dispatch"]) for a in assemblies if a["dispatch"]]
    gfcs = [_as_date(a["gfc"]) for a in assemblies if a["gfc"]]
    cars = next((a["cars"] for a in assemblies if a["cars"] is not None), None)

    project = Project(
        code=code_service.next_code(db, "project"),
        name=name,
        product_id=product.id,
        design_manager_id=manager.id if manager else None,
        created_by_id=manager.id if manager else None,
        status=ProjectStatus.DESIGN_IN_PROGRESS.value,
        project_type=RELEASE_TYPE,
        car_count=cars,
        gfc_date=min(gfcs) if gfcs else None,
        customer_deadline=max(dispatches) if dispatches else None,
        required_completion_date=max(dispatches) if dispatches else None,
        description=(
            f"Imported from the {data['source']}. {len(assemblies)} assemblies."
        ),
    )
    db.add(project)
    db.flush()

    task_count = 0
    for sequence, item in enumerate(assemblies, start=1):
        phases = item["phases"]
        planned = [_as_date(p["planned_end"]) for p in phases.values() if p["planned_end"]]
        actuals = [_as_date(p["actual_end"]) for p in phases.values() if p["actual_end"]]

        release = DesignRelease(
            code=code_service.next_code(db, "release"),
            project_id=project.id,
            sequence_number=sequence,
            name=item["assembly"],
            release_type=RELEASE_TYPE,
            product_id=product.id,
            template_version_id=version.id,
            dsq_count=item["dsqs"],
            planned_start=min(planned) - timedelta(days=14) if planned else None,
            planned_end=max(planned) if planned else None,
            actual_end=max(actuals) if actuals else None,
            status=ReleaseStatus.IN_PROGRESS.value,
            description=item["remarks"],
            created_by_id=manager.id if manager else None,
        )
        db.add(release)
        db.flush()

        for index, (phase_name, task_type) in enumerate(PHASE_ORDER, start=1):
            phase = phases.get(phase_name)
            if phase is None:
                continue
            percent = phase["completion_percent"]
            done = phase["completed"] or (percent is not None and percent >= 100)
            status = (
                TaskStatus.COMPLETED.value
                if done
                else TaskStatus.IN_PROGRESS.value
                if percent
                else TaskStatus.NOT_STARTED.value
            )
            task = Task(
                code=code_service.next_code(db, "task"),
                project_id=project.id,
                release_id=release.id,
                sequence=index,
                name=phase_name,
                task_type=task_type,
                status=status,
                # The tracker records no effort, so none is invented here.
                estimated_hours=0,
                original_estimated_hours=0,
                completion_percent=100.0 if done else (percent or 0.0),
                planned_end=_as_date(phase["planned_end"]),
                is_mandatory=True,
                requires_review=phase_name in GATING,
                created_by_id=manager.id if manager else None,
            )
            actual = _as_date(phase["actual_end"])
            if actual:
                task.completed_at = actual
            db.add(task)
            task_count += 1

        db.flush()
        rollup_service.refresh_release(db, release)

    rollup_service.refresh_project(db, project)
    db.flush()

    return {
        "project": project.code,
        "name": name,
        "releases": len(assemblies),
        "tasks": task_count,
        "demo_projects_removed": removed,
    }
