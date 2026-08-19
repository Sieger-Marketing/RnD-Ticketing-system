"""Product design template endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, NotFoundError
from app.core.deps import require_permission
from app.core.permissions import P
from app.db.session import get_db
from app.models.catalog import Product
from app.models.template import DesignTemplate, DesignTemplateVersion, TemplateTask
from app.models.user import User
from app.schemas.common import Message
from app.schemas.workflow import (
    DraftVersionCreate,
    TemplateCreate,
    TemplateOut,
    TemplateTaskIn,
    TemplateTaskOut,
    TemplateVersionOut,
)
from app.services import code_service, template_service

router = APIRouter(prefix="/templates", tags=["templates"])


def _version_out(version: DesignTemplateVersion, with_tasks: bool = True) -> TemplateVersionOut:
    return TemplateVersionOut(
        id=version.id,
        version_number=version.version_number,
        label=version.label,
        is_published=version.is_published,
        published_at=version.published_at,
        change_note=version.change_note,
        task_count=len(version.tasks),
        total_estimated_hours=round(
            sum(float(t.default_estimated_hours or 0) for t in version.tasks), 2
        ),
        tasks=[
            TemplateTaskOut(
                id=t.id,
                sequence=t.sequence,
                name=t.name,
                task_type=t.task_type,
                description=t.description,
                default_estimated_hours=float(t.default_estimated_hours or 0),
                default_priority=t.default_priority,
                complexity=t.complexity,
                required_skill_id=t.required_skill_id,
                is_mandatory=t.is_mandatory,
                requires_review=t.requires_review,
                depends_on_sequence=t.depends_on_sequence,
                depends_on_blocking=t.depends_on_blocking,
                required_skill_name=t.required_skill.name if t.required_skill else None,
            )
            for t in version.tasks
        ]
        if with_tasks
        else [],
    )


def _template_out(template: DesignTemplate, with_tasks: bool = True) -> TemplateOut:
    current = template.current_version
    return TemplateOut(
        id=template.id,
        code=template.code,
        name=template.name,
        description=template.description,
        release_type=template.release_type,
        product_id=template.product_id,
        product_name=template.product.name if template.product else None,
        product_family_id=template.product_family_id,
        product_family_name=(
            template.product_family.name if template.product_family else None
        ),
        is_active=template.is_active,
        current_version_number=current.version_number if current else None,
        versions=[_version_out(v, with_tasks) for v in template.versions],
    )


@router.get("", response_model=list[TemplateOut])
def list_templates(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(P.TEMPLATE_VIEW)),
    release_type: str | None = None,
    product_id: uuid.UUID | None = None,
    product_family_id: uuid.UUID | None = None,
    active_only: bool = True,
    include_tasks: bool = Query(False, description="Include each version's task list"),
) -> list[TemplateOut]:
    stmt = select(DesignTemplate)
    if release_type:
        stmt = stmt.where(DesignTemplate.release_type == release_type)
    if product_id:
        stmt = stmt.where(DesignTemplate.product_id == product_id)
    if product_family_id:
        stmt = stmt.where(DesignTemplate.product_family_id == product_family_id)
    if active_only:
        stmt = stmt.where(DesignTemplate.is_active.is_(True))

    rows = db.execute(stmt.order_by(DesignTemplate.name)).scalars().all()
    return [_template_out(t, include_tasks) for t in rows]


@router.get("/match")
def match_templates(
    release_type: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(P.TEMPLATE_VIEW)),
    product_id: uuid.UUID | None = None,
    product_family_id: uuid.UUID | None = None,
) -> dict:
    """Which template the system would suggest for a product + release type."""
    if product_id and product_family_id is None:
        product = db.get(Product, product_id)
        product_family_id = product.product_family_id if product else None

    suggestion = template_service.suggest_template(
        db,
        product_id=product_id,
        product_family_id=product_family_id,
        release_type=release_type,
    )
    matches = template_service.find_matching_templates(
        db,
        product_id=product_id,
        product_family_id=product_family_id,
        release_type=release_type,
    )
    return {
        "suggested_version_id": str(suggestion.id) if suggestion else None,
        "suggested_template": suggestion.template.name if suggestion else None,
        "matches": [_template_out(t, with_tasks=False).model_dump() for t in matches],
    }


@router.post("", response_model=TemplateOut, status_code=201)
def create_template(
    payload: TemplateCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(P.TEMPLATE_MANAGE)),
) -> TemplateOut:
    """Create a template with its first draft version."""
    template = DesignTemplate(
        code=code_service.next_code(db, "template"),
        name=payload.name,
        description=payload.description,
        release_type=payload.release_type,
        product_id=payload.product_id,
        product_family_id=payload.product_family_id,
        created_by_id=user.id,
    )
    db.add(template)
    db.flush()

    version = DesignTemplateVersion(
        template_id=template.id, version_number=1, is_published=False
    )
    db.add(version)
    db.flush()

    for task in payload.tasks:
        db.add(TemplateTask(version_id=version.id, **task.model_dump()))
    db.flush()
    db.refresh(template)
    return _template_out(template)


@router.get("/{template_id}", response_model=TemplateOut)
def get_template(
    template_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(P.TEMPLATE_VIEW)),
) -> TemplateOut:
    template = db.get(DesignTemplate, template_id)
    if template is None:
        raise NotFoundError("Template not found.")
    return _template_out(template)


@router.post("/{template_id}/versions", response_model=TemplateVersionOut, status_code=201)
def create_draft(
    template_id: uuid.UUID,
    payload: DraftVersionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(P.TEMPLATE_MANAGE)),
) -> TemplateVersionOut:
    """Open a new draft version, copying the current published tasks."""
    template = db.get(DesignTemplate, template_id)
    if template is None:
        raise NotFoundError("Template not found.")
    draft = template_service.create_draft_version(
        db, template, actor=user, change_note=payload.change_note
    )
    return _version_out(draft)


@router.put("/versions/{version_id}/tasks", response_model=TemplateVersionOut)
def replace_version_tasks(
    version_id: uuid.UUID,
    tasks: list[TemplateTaskIn],
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(P.TEMPLATE_MANAGE)),
) -> TemplateVersionOut:
    """Replace a draft version's task list.

    Refused on a published version: releases already generated from it would
    otherwise silently change shape (spec section 9).
    """
    version = template_service.get_version_or_404(db, version_id)
    if version.is_published:
        raise BusinessRuleError(
            "A published template version is immutable. Create a new draft version "
            "to make changes."
        )

    sequences = [t.sequence for t in tasks]
    if len(sequences) != len(set(sequences)):
        raise BusinessRuleError("Template task sequence numbers must be unique.")

    for existing in list(version.tasks):
        db.delete(existing)
    db.flush()

    for task in tasks:
        db.add(TemplateTask(version_id=version.id, **task.model_dump()))
    db.flush()
    db.refresh(version)
    return _version_out(version)


@router.post("/versions/{version_id}/publish", response_model=TemplateVersionOut)
def publish_version(
    version_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(P.TEMPLATE_PUBLISH)),
) -> TemplateVersionOut:
    version = template_service.get_version_or_404(db, version_id)
    template_service.publish_version(db, version, actor=user)
    return _version_out(version)


@router.get("/versions/{version_id}", response_model=TemplateVersionOut)
def get_version(
    version_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(P.TEMPLATE_VIEW)),
) -> TemplateVersionOut:
    return _version_out(template_service.get_version_or_404(db, version_id))


@router.delete("/{template_id}", response_model=Message)
def deactivate_template(
    template_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(P.TEMPLATE_MANAGE)),
) -> Message:
    """Deactivate rather than delete, so pinned versions keep resolving."""
    template = db.get(DesignTemplate, template_id)
    if template is None:
        raise NotFoundError("Template not found.")
    template.is_active = False
    db.flush()
    return Message(message=f"Template {template.code} deactivated.")
