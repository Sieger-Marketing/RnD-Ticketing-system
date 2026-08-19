"""Bootstrap: the rows the application cannot run without.

Permissions, the four roles and their grants, and the default configuration.
Idempotent -- running it against a populated database only fills gaps, so it
is safe to re-run after adding a permission in code.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import RoleName
from app.core.permissions import (
    DEFAULT_ROLE_PERMISSIONS,
    PERMISSION_CATALOG,
    ROLE_RANKS,
)
from app.core.config import settings
from app.core.security import hash_password
from app.models.user import Permission, Role, RolePermission, User, UserRole
from app.services import code_service, settings_service

ROLE_DESCRIPTIONS = {
    RoleName.DIRECTOR.value: "Executive visibility across the department. Read-only.",
    RoleName.DESIGN_MANAGER.value: "Full operational control of projects, releases, "
    "templates, resources and configuration.",
    RoleName.TEAM_LEAD.value: "Owns design releases, plans and assigns tasks, "
    "reviews work and manages team workload.",
    RoleName.DESIGNER.value: "Executes assigned tasks, logs time and submits work "
    "for review.",
}


def sync_permissions(db: Session) -> int:
    """Insert any permission defined in code but missing from the database."""
    existing = {code for (code,) in db.execute(select(Permission.code)).all()}
    added = 0
    for code, (module, description) in PERMISSION_CATALOG.items():
        if code in existing:
            continue
        db.add(Permission(code=code, module=module, description=description))
        added += 1
    if added:
        db.flush()
    return added


def sync_roles(db: Session) -> int:
    added = 0
    for name, rank in ROLE_RANKS.items():
        role = db.execute(select(Role).where(Role.name == name)).scalar_one_or_none()
        if role is None:
            db.add(
                Role(
                    name=name,
                    rank=rank,
                    description=ROLE_DESCRIPTIONS.get(name),
                    is_system=True,
                )
            )
            added += 1
    if added:
        db.flush()
    return added


def sync_role_permissions(db: Session) -> int:
    """Grant each role its default permissions, without revoking custom grants.

    Only additive on purpose: an administrator who granted a role an extra
    permission should not lose it because the application restarted.
    """
    permissions = {
        p.code: p for p in db.execute(select(Permission)).scalars()
    }
    roles = {r.name: r for r in db.execute(select(Role)).scalars()}

    existing = {
        (rp.role_id, rp.permission_id)
        for rp in db.execute(select(RolePermission)).scalars()
    }

    added = 0
    for role_name, codes in DEFAULT_ROLE_PERMISSIONS.items():
        role = roles.get(role_name)
        if role is None:
            continue
        for code in codes:
            permission = permissions.get(code)
            if permission is None:
                continue
            if (role.id, permission.id) in existing:
                continue
            db.add(RolePermission(role_id=role.id, permission_id=permission.id))
            added += 1
    if added:
        db.flush()
    return added


def ensure_administrator(db: Session) -> str | None:
    """Create the administrator account if it is missing.

    Address and password come from the environment, so the one account that can
    do anything is never a value sitting in this repository. Existing accounts
    are left alone: this runs on every deploy, and resetting somebody's
    password on each push would be its own kind of outage.
    """
    email = settings.ADMIN_EMAIL.strip().lower()
    if not email:
        return None

    if db.execute(select(User).where(User.email == email)).scalar_one_or_none():
        return None

    role = db.execute(
        select(Role).where(Role.name == RoleName.ADMINISTRATOR.value)
    ).scalar_one_or_none()
    if role is None:
        return None

    user = User(
        code=code_service.next_code(db, "user"),
        email=email,
        full_name=settings.ADMIN_NAME,
        designation="System Administrator",
        department="Design",
        hashed_password=hash_password(settings.SEED_DEFAULT_PASSWORD),
        is_active=True,
    )
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_id=role.id))
    db.flush()
    return email


def run(db: Session) -> dict[str, int]:
    result = {
        "permissions_added": sync_permissions(db),
        "roles_added": sync_roles(db),
    }
    result["role_permissions_added"] = sync_role_permissions(db)
    result["settings_added"] = settings_service.ensure_defaults(db)
    created = ensure_administrator(db)
    if created:
        result["administrator_created"] = created
    return result
