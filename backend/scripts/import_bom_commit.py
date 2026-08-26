"""Write one BOM project into the database, as a proof of concept.

Imports a single project from the design team's tracker: its products, the
assemblies as design releases, and the five phases as tasks carrying the plan
dates, actual dates and completion the sheet already records.

Also publishes a "BOM Release" template of those five phases, so releases the
team creates from now on generate the same structure rather than being typed
out each time.

The sheet names nobody and records no hours, so tasks arrive unassigned with
no estimate. Schedule and completion are real from the first minute; capacity
and efficiency begin the day people start logging time.

Idempotent: running it twice replaces the imported project rather than
doubling it.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.core.enums import ProjectStatus, ReleaseStatus, TaskStatus  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.catalog import Product, ProductFamily  # noqa: E402
from app.models.project import Project  # noqa: E402
from app.models.release import DesignRelease  # noqa: E402
from app.models.task import Task  # noqa: E402
from app.models.template import (  # noqa: E402
    DesignTemplate,
    DesignTemplateVersion,
    TemplateTask,
)
from app.models.user import User  # noqa: E402
from app.services import code_service, rollup_service  # noqa: E402
from scripts.import_bom import PHASES, read  # noqa: E402

RELEASE_TYPE = "BOM Release"

#: Phases whose input must exist before they can begin. A drawing release
#: cannot precede the 3D model it is taken from, but concept and long-lead
#: procurement genuinely overlap in practice.
GATING_PHASES = {"Mfg. Release", "Packing list & Stuffing"}


def ensure_products(db, names: set[str]) -> dict[str, Product]:
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

    products: dict[str, Product] = {}
    for name in sorted(names):
        product = db.execute(
            select(Product).where(Product.name == name)
        ).scalar_one_or_none()
        if product is None:
            product = Product(
                code=code_service.next_code(db, "product"),
                name=name,
                product_family_id=family.id,
                description=f"{name} system.",
            )
            db.add(product)
            db.flush()
        products[name] = product
    return products


def ensure_template(db, author: User, product: Product | None) -> DesignTemplateVersion:
    """The five phases, as a published template."""
    template = db.execute(
        select(DesignTemplate).where(DesignTemplate.name == "BOM Release — Standard")
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

    if template is None:
        template = DesignTemplate(
            code=code_service.next_code(db, "template"),
            name="BOM Release — Standard",
            release_type=RELEASE_TYPE,
            product_family_id=product.product_family_id if product else None,
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

    for index, (name, _, _, _, task_type) in enumerate(PHASES, start=1):
        db.add(
            TemplateTask(
                version_id=version.id,
                sequence=index,
                name=name,
                task_type=task_type,
                default_estimated_hours=0,
                complexity=3,
                is_mandatory=True,
                requires_review=name in GATING_PHASES,
                depends_on_sequence=index - 1 if index > 1 else None,
                depends_on_blocking=name in GATING_PHASES,
            )
        )
    db.flush()
    template.current_version_id = version.id
    db.flush()
    return version


def status_for(percent: float | None, completed: bool) -> str:
    if completed or (percent is not None and percent >= 100):
        return TaskStatus.COMPLETED.value
    if percent:
        return TaskStatus.IN_PROGRESS.value
    return TaskStatus.NOT_STARTED.value


def run(workbook: Path, project_name: str, keep_demo: str | None) -> None:
    rows = [r for r in read(workbook) if r.project_is_usable and r.project == project_name]
    if not rows:
        raise SystemExit(f"No rows found for project {project_name!r}")

    db = SessionLocal()
    try:
        manager = db.execute(
            select(User).where(User.email.like("lakshmi%"))
        ).scalars().first() or db.execute(select(User)).scalars().first()

        # --- trim the demonstration department ----------------------------
        if keep_demo:
            keep = db.execute(
                select(Project).where(Project.name == keep_demo)
            ).scalar_one_or_none()
            removed = 0
            for project in db.execute(select(Project)).scalars().all():
                if keep and project.id == keep.id:
                    continue
                db.delete(project)
                removed += 1
            db.flush()
            print(f"Removed {removed} demo projects, kept {keep_demo!r}")

        products = ensure_products(db, {r.product for r in rows})
        product = products[rows[0].product]
        version = ensure_template(db, manager, product)
        print(f"Template: BOM Release — Standard v{version.version_number} ({len(PHASES)} phases)")

        existing = db.execute(
            select(Project).where(Project.name == project_name)
        ).scalar_one_or_none()
        if existing:
            db.delete(existing)
            db.flush()
            print(f"Replaced the previous import of {project_name!r}")

        dispatches = [r.dispatch for r in rows if r.dispatch]
        gfcs = [r.gfc for r in rows if r.gfc]
        cars = next((r.cars for r in rows if r.cars is not None), None)

        project = Project(
            code=code_service.next_code(db, "project"),
            name=project_name,
            product_id=product.id,
            team_lead_id=None,  # assigned by a manager once the work is scheduled
            created_by_id=manager.id if manager else None,
            status=ProjectStatus.DESIGN_IN_PROGRESS.value,
            project_type="BOM Release",
            car_count=cars,
            gfc_date=min(gfcs) if gfcs else None,
            customer_deadline=max(dispatches) if dispatches else None,
            required_completion_date=max(dispatches) if dispatches else None,
            description=(
                f"Imported from the design team's BOM release tracker. "
                f"{len(rows)} assemblies."
            ),
        )
        db.add(project)
        db.flush()

        task_total = 0
        for sequence, row in enumerate(rows, start=1):
            planned = [p["planned_end"] for p in row.phases.values() if p["planned_end"]]
            actuals = [p["actual_end"] for p in row.phases.values() if p["actual_end"]]

            release = DesignRelease(
                code=code_service.next_code(db, "release"),
                project_id=project.id,
                sequence_number=sequence,
                name=row.assembly,
                release_type=RELEASE_TYPE,
                product_id=product.id,
                template_version_id=version.id,
                dsq_count=row.dsqs,
                planned_start=min(planned) - timedelta(days=14) if planned else None,
                planned_end=max(planned) if planned else None,
                actual_end=max(actuals) if actuals else None,
                status=ReleaseStatus.IN_PROGRESS.value,
                description=row.remarks,
                created_by_id=manager.id if manager else None,
            )
            db.add(release)
            db.flush()

            for index, (name, _, _, _, task_type) in enumerate(PHASES, start=1):
                phase = row.phases.get(name)
                if phase is None:
                    continue
                percent = phase["completion_percent"]
                status = status_for(percent, phase["completed"])
                task = Task(
                    code=code_service.next_code(db, "task"),
                    project_id=project.id,
                    release_id=release.id,
                    sequence=index,
                    name=name,
                    task_type=task_type,
                    status=status,
                    # The sheet records no effort, so nothing is invented here.
                    estimated_hours=0,
                    original_estimated_hours=0,
                    completion_percent=(
                        100.0 if status == TaskStatus.COMPLETED.value else (percent or 0.0)
                    ),
                    planned_end=phase["planned_end"],
                    is_mandatory=True,
                    requires_review=name in GATING_PHASES,
                    created_by_id=manager.id if manager else None,
                )
                if phase["actual_end"]:
                    task.completed_at = phase["actual_end"]
                db.add(task)
                task_total += 1
            db.flush()
            rollup_service.refresh_release(db, release)

        rollup_service.refresh_project(db, project)
        db.commit()

        print(
            f"\nImported {project.code} {project.name}\n"
            f"  product      {product.name}\n"
            f"  releases     {len(rows)}\n"
            f"  tasks        {task_total}\n"
            f"  cars         {project.car_count}\n"
            f"  GFC          {project.gfc_date}\n"
            f"  dispatch     {project.customer_deadline}\n"
            f"  completion   {project.completion_percent:.0f}%\n"
            f"  health       {project.health}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--project", required=True)
    parser.add_argument(
        "--keep-demo",
        help="Name of the one demo project to keep; all others are removed.",
    )
    args = parser.parse_args()
    run(args.workbook, args.project, args.keep_demo)
