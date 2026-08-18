"""Configuration and audit endpoints (spec sections 30 and 34)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import client_context, get_current_user, require_permission
from app.core.enums import AuditAction
from app.core.errors import NotFoundError, ValidationError
from app.core.permissions import PERMISSION_CATALOG, P
from app.db.session import get_db
from app.models.system import AppSetting, AuditLog, StatusHistory
from app.models.user import User
from app.schemas.common import Page
from app.schemas.execution import (
    AuditLogOut,
    SettingOut,
    SettingUpdate,
    StatusHistoryOut,
)
from app.services import audit_service, settings_service

router = APIRouter(tags=["settings"])


@router.get("/settings", response_model=list[SettingOut])
def list_settings(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(P.SETTINGS_VIEW)),
    category: str | None = None,
) -> list[SettingOut]:
    stmt = select(AppSetting)
    if category:
        stmt = stmt.where(AppSetting.category == category)
    rows = db.execute(stmt.order_by(AppSetting.category, AppSetting.key)).scalars().all()
    return [SettingOut.model_validate(s) for s in rows]


@router.get("/settings/{key}", response_model=SettingOut)
def get_setting(
    key: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(P.SETTINGS_VIEW)),
) -> SettingOut:
    row = db.execute(select(AppSetting).where(AppSetting.key == key)).scalar_one_or_none()
    if row is None:
        raise NotFoundError(f"Setting '{key}' not found.")
    return SettingOut.model_validate(row)


@router.put("/settings/{key}", response_model=SettingOut)
def update_setting(
    key: str,
    payload: SettingUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(P.SETTINGS_MANAGE)),
) -> SettingOut:
    existing = db.execute(
        select(AppSetting).where(AppSetting.key == key)
    ).scalar_one_or_none()
    before = existing.value if existing else None

    _validate_setting(key, payload.value)

    row = settings_service.set_setting(db, key, payload.value, updated_by_id=user.id)
    audit_service.record(
        db,
        entity_type="app_setting",
        entity_id=row.id,
        entity_code=key,
        action=AuditAction.UPDATE,
        actor=user,
        summary=f"Changed setting '{key}'",
        old_value={"value": before},
        new_value={"value": payload.value},
        context=client_context(request),
    )
    return SettingOut.model_validate(row)


def _validate_setting(key: str, value) -> None:
    """Guard the settings the engines cannot survive being nonsense.

    A malformed threshold set would silently mis-rate every project, so the
    few settings with structural requirements are checked on write rather
    than discovered at read time.
    """
    if key == "kpi.performance_weights":
        if not isinstance(value, dict):
            raise ValidationError("Performance weights must be an object.")
        total = sum(float(v) for v in value.values())
        if abs(total - 100) > 0.01:
            raise ValidationError(
                f"Performance weights must total 100, got {total:g}."
            )
    if key == "capacity.thresholds":
        if not isinstance(value, dict):
            raise ValidationError("Capacity thresholds must be an object.")
        required = ["underutilized", "healthy", "high_load"]
        missing = [k for k in required if k not in value]
        if missing:
            raise ValidationError(f"Missing threshold(s): {', '.join(missing)}")
        under, healthy, high = (float(value[k]) for k in required)
        if not under < healthy <= high:
            raise ValidationError(
                "Thresholds must increase: underutilized < healthy <= high_load."
            )
    if key == "capacity.working_days":
        if not isinstance(value, list) or not value:
            raise ValidationError("Working days must be a non-empty list.")
        if any(not isinstance(d, int) or d < 0 or d > 6 for d in value):
            raise ValidationError("Working days must be integers 0 (Mon) to 6 (Sun).")

    # The two accountability-bearing vocabularies are lists of objects; the
    # plain ones are lists of strings. Saving the wrong shape does not fail
    # here without this check -- it fails later inside the overdue-submit path,
    # where `r["value"]` on a string raises TypeError, turning an admin's typo
    # into a 500 for every designer. It would also make accountability_for()
    # fall through to "Controllable", quietly booking all rework against the
    # team that raised it.
    if key in {"workflow.delay_reasons", "workflow.revision_categories"}:
        if not isinstance(value, list) or not value:
            raise ValidationError(f"{key} must be a non-empty list.")
        for entry in value:
            if not isinstance(entry, dict) or "value" not in entry:
                raise ValidationError(
                    f"Each {key} entry must be an object with a 'value' key, "
                    'for example {"value": "Customer Change", '
                    '"accountability": "External"}.'
                )
            if entry.get("accountability") not in {"Controllable", "External"}:
                raise ValidationError(
                    f"'{entry['value']}' needs an accountability of "
                    "'Controllable' or 'External'; it decides whether the "
                    "rework counts against the team."
                )

    if key in {
        "workflow.task_types",
        "workflow.release_types",
        "workflow.project_types",
    }:
        if not isinstance(value, list) or not value:
            raise ValidationError(f"{key} must be a non-empty list.")
        if any(not isinstance(v, str) or not v.strip() for v in value):
            raise ValidationError(f"Every {key} entry must be a non-empty string.")


@router.get("/settings/meta/permissions")
def permission_catalog(
    _: User = Depends(require_permission(P.SETTINGS_VIEW)),
) -> list[dict]:
    """Every permission the application understands."""
    return [
        {"code": code, "module": module, "description": description}
        for code, (module, description) in sorted(PERMISSION_CATALOG.items())
    ]


@router.get("/audit-logs", response_model=Page[AuditLogOut])
def list_audit_logs(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(P.AUDIT_VIEW)),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    entity_code: str | None = None,
    action: str | None = None,
    actor_id: uuid.UUID | None = None,
) -> Page[AuditLogOut]:
    stmt = select(AuditLog)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if entity_code:
        stmt = stmt.where(AuditLog.entity_code == entity_code)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if actor_id:
        stmt = stmt.where(AuditLog.actor_id == actor_id)

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar() or 0
    rows = (
        db.execute(
            stmt.order_by(AuditLog.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    return Page.build(
        [AuditLogOut.model_validate(r) for r in rows], total, page, page_size
    )


@router.get("/status-history", response_model=list[StatusHistoryOut])
def status_history(
    entity_type: str,
    entity_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[StatusHistoryOut]:
    rows = (
        db.execute(
            select(StatusHistory)
            .where(
                StatusHistory.entity_type == entity_type,
                StatusHistory.entity_id == entity_id,
            )
            .order_by(StatusHistory.changed_at)
        )
        .scalars()
        .all()
    )
    return [StatusHistoryOut.model_validate(r) for r in rows]
