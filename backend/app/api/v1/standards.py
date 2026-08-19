"""Standard design releases: read a product's list, apply it to a project."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import client_context, get_current_user, require_permission
from app.core.permissions import P
from app.db.session import get_db
from app.models.catalog import Product
from app.models.project import Project
from app.models.task import Task
from app.models.template import TemplateTask
from app.models.user import User
from app.core.errors import NotFoundError, ValidationError
from app.schemas.catalog import (
    ApplyStandard,
    ProductStandardOut,
    ReleaseStandardOut,
    StandardVariantOut,
)
from app.schemas.workflow import ReleaseSummary
from app.services import standard_service

router = APIRouter(tags=["standards"])


def _shared_task_names(db: Session) -> list[str]:
    version = standard_service.shared_version(db)
    if version is None:
        return []
    return list(
        db.execute(
            select(TemplateTask.name)
            .where(TemplateTask.version_id == version.id)
            .order_by(TemplateTask.sequence)
        ).scalars()
    )


def _standard(db: Session, product: Product) -> ProductStandardOut:
    return ProductStandardOut(
        product_id=product.id,
        product_name=product.name,
        tasks=_shared_task_names(db),
        variants=[
            StandardVariantOut(
                variant=group["variant"],
                condition=group["condition"],
                releases=[ReleaseStandardOut.model_validate(r) for r in group["releases"]],
            )
            for group in standard_service.variants(db, product.id)
        ],
    )


@router.get("/release-standards", response_model=list[ProductStandardOut])
def list_standards(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[ProductStandardOut]:
    """Every product's standard -- the reference chart, in one call."""
    products = (
        db.execute(select(Product).where(Product.is_active.is_(True)).order_by(Product.name))
        .scalars()
        .all()
    )
    return [s for p in products if (s := _standard(db, p)).variants]


@router.get("/products/{product_id}/release-standard", response_model=ProductStandardOut)
def get_product_standard(
    product_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> ProductStandardOut:
    return _standard(db, standard_service.product_or_404(db, product_id))


@router.post(
    "/projects/{project_id}/apply-standard",
    response_model=list[ReleaseSummary],
    status_code=201,
)
def apply_standard(
    project_id: uuid.UUID,
    payload: ApplyStandard,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(P.RELEASE_CREATE)),
) -> list[ReleaseSummary]:
    """Create the chosen standard releases on a project, with their tasks."""
    project = db.get(Project, project_id)
    if project is None:
        raise NotFoundError("Project not found.")
    if project.product_id is None:
        raise ValidationError(
            "This project has no product, so there is no standard to apply. "
            "Set the project's product first."
        )

    product = standard_service.product_or_404(db, project.product_id)
    created = standard_service.apply_to_project(
        db,
        project=project,
        product=product,
        variant=payload.variant,
        standard_ids=payload.release_ids,
        actor=user,
        context=client_context(request),
        generate_tasks=payload.generate_tasks,
        planned_start=payload.planned_start,
    )
    counts = dict(
        db.execute(
            select(Task.release_id, func.count())
            .where(Task.release_id.in_([r.id for r in created]))
            .group_by(Task.release_id)
        ).all()
    )
    return [ReleaseSummary.from_model(r, counts.get(r.id, 0)) for r in created]
