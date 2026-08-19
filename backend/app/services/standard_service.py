"""Reading a product's standard design releases, and applying them to a project.

The standard answers "what does a Tower project release?" -- the design team's
own list, not something a coordinator retypes per project. Applying it creates
the real releases and, through the shared template, the five tasks under each.

Nothing here is automatic. A conditional release (Foundation above 3 levels,
Ceiling Supports at 2) is *offered* with its rule attached; the manager decides.
Once created, a release is ordinary work -- editable, deletable, and free to
diverge from the standard, which is only ever a starting point.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import AuditAction, ReleaseStatus
from app.core.errors import NotFoundError, ValidationError
from app.models.catalog import Product
from app.models.project import Project
from app.models.release import DesignRelease
from app.models.standard import ReleaseStandard
from app.models.template import DesignTemplate, DesignTemplateVersion
from app.models.user import User
from app.services import audit_service, code_service, rollup_service, template_service

#: The template every standard release is generated from. Kept by name because
#: the design team owns one shared task list, not one per product.
SHARED_TEMPLATE_NAME = "Standard Design Release"

DEFAULT_RELEASE_TYPE = "Design Release"


def for_product(db: Session, product_id: uuid.UUID) -> list[ReleaseStandard]:
    return list(
        db.execute(
            select(ReleaseStandard)
            .where(ReleaseStandard.product_id == product_id)
            .order_by(ReleaseStandard.variant, ReleaseStandard.sequence)
        )
        .scalars()
        .all()
    )


def variants(db: Session, product_id: uuid.UUID) -> list[dict]:
    """Group a product's standard into its named sets, in a stable order.

    "standard" always leads; a Stacker's small-system set follows it.
    """
    grouped: dict[str, dict] = {}
    for row in for_product(db, product_id):
        bucket = grouped.setdefault(
            row.variant,
            {"variant": row.variant, "condition": row.variant_condition, "releases": []},
        )
        bucket["releases"].append(row)

    ordered = sorted(grouped.values(), key=lambda v: (v["variant"] != "standard", v["variant"]))
    return ordered


def shared_version(db: Session) -> DesignTemplateVersion | None:
    """The published version of the five-task template, if it exists."""
    return (
        db.execute(
            select(DesignTemplateVersion)
            .join(DesignTemplate, DesignTemplate.id == DesignTemplateVersion.template_id)
            .where(
                DesignTemplate.name == SHARED_TEMPLATE_NAME,
                DesignTemplateVersion.is_published.is_(True),
            )
            .order_by(DesignTemplateVersion.version_number.desc())
        )
        .scalars()
        .first()
    )


def apply_to_project(
    db: Session,
    *,
    project: Project,
    product: Product,
    variant: str,
    standard_ids: list[uuid.UUID],
    actor: User,
    context: dict | None = None,
    generate_tasks: bool = True,
    planned_start: date | None = None,
) -> list[DesignRelease]:
    """Create one release per chosen standard row, appended to the project.

    Existing releases are left alone and numbering continues after them, so a
    project that already has work can still be topped up from the standard.
    """
    rows = {
        row.id: row
        for row in for_product(db, product.id)
        if row.variant == variant
    }
    chosen = [rows[sid] for sid in standard_ids if sid in rows]
    if not chosen:
        raise ValidationError(
            "None of the selected releases belong to this product's standard."
        )

    missing = [str(sid) for sid in standard_ids if sid not in rows]
    if missing:
        raise ValidationError(
            "Some selected releases are not part of this product's "
            f"{variant} standard: {', '.join(missing)}."
        )

    chosen.sort(key=lambda r: r.sequence)

    taken = {
        name.strip().lower()
        for name in db.execute(
            select(DesignRelease.name).where(DesignRelease.project_id == project.id)
        ).scalars()
    }

    next_sequence = (
        db.execute(
            select(func.coalesce(func.max(DesignRelease.sequence_number), 0)).where(
                DesignRelease.project_id == project.id
            )
        ).scalar()
        or 0
    )

    version = shared_version(db) if generate_tasks else None
    created: list[DesignRelease] = []

    for row in chosen:
        # Re-applying a standard should not duplicate what is already there.
        if row.name.strip().lower() in taken:
            continue

        next_sequence += 1
        release = DesignRelease(
            code=code_service.next_code(db, "release"),
            project_id=project.id,
            sequence_number=next_sequence,
            name=row.name,
            release_type=DEFAULT_RELEASE_TYPE,
            description=row.condition,
            product_id=product.id,
            priority=project.priority,
            planned_start=planned_start,
            status=ReleaseStatus.DRAFT.value,
            created_by_id=actor.id,
        )
        db.add(release)
        db.flush()
        taken.add(row.name.strip().lower())

        audit_service.record(
            db,
            entity_type="design_release",
            entity_id=release.id,
            entity_code=release.code,
            action=AuditAction.CREATE,
            actor=actor,
            summary=(
                f"Created {release.code} - {release.name} "
                f"from the {product.name} standard"
            ),
            context=context,
        )

        if version is not None:
            template_service.generate_tasks_for_release(
                db, release, version, actor=actor, context=context
            )

        rollup_service.refresh_release(db, release)
        created.append(release)

    if not created:
        raise ValidationError(
            "Every selected release already exists on this project."
        )

    rollup_service.refresh_project(db, project)
    return created


def product_or_404(db: Session, product_id: uuid.UUID) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise NotFoundError("Product not found.")
    return product
