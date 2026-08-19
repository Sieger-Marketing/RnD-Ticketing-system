"""User, role and skill administration."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.deps import client_context, get_current_user, require_permission
from app.core.enums import AuditAction
from app.core.errors import NotFoundError, ValidationError
from app.core.permissions import P
from app.core.security import hash_password
from app.db.session import get_db
from app.models.user import Role, Skill, User, UserRole, UserSkill
from app.schemas.common import Message, Page
from app.schemas.people import (
    RoleOut,
    SkillCreate,
    SkillOut,
    UserCreate,
    UserOut,
    UserSkillAssign,
    UserUpdate,
    SKILL_LEVEL_RANK,
)
from app.services import audit_service, code_service

router = APIRouter(tags=["users"])


def _roles_by_name(db: Session, names: list[str]) -> list[Role]:
    rows = db.execute(select(Role).where(Role.name.in_(names))).scalars().all()
    found = {r.name for r in rows}
    missing = [n for n in names if n not in found]
    if missing:
        raise ValidationError(f"Unknown role(s): {', '.join(missing)}")
    return list(rows)


@router.get("/users", response_model=Page[UserOut])
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(P.USER_VIEW)),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    role: str | None = None,
    reports_to_id: uuid.UUID | None = None,
    active_only: bool = True,
    search: str | None = None,
) -> Page[UserOut]:
    stmt = select(User)
    if active_only:
        stmt = stmt.where(User.is_active.is_(True))
    if reports_to_id:
        stmt = stmt.where(User.reports_to_id == reports_to_id)
    if role:
        stmt = stmt.where(
            User.id.in_(
                select(UserRole.user_id)
                .join(Role, Role.id == UserRole.role_id)
                .where(Role.name == role)
            )
        )
    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                User.full_name.ilike(pattern),
                User.email.ilike(pattern),
                User.code.ilike(pattern),
            )
        )

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar() or 0
    rows = (
        db.execute(
            stmt.order_by(User.full_name).offset((page - 1) * page_size).limit(page_size)
        )
        .scalars()
        .all()
    )
    return Page.build([UserOut.from_model(u) for u in rows], total, page, page_size)


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(
    payload: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(P.USER_MANAGE)),
) -> UserOut:
    email = payload.email.lower()
    if db.execute(select(User.id).where(User.email == email)).first():
        raise ValidationError("A user with that email address already exists.")

    employee_code = payload.employee_code.strip().upper() if payload.employee_code else None
    if employee_code and db.execute(
        select(User.id).where(User.employee_code == employee_code)
    ).first():
        raise ValidationError(
            f"Employee code {employee_code} already belongs to another account."
        )

    roles = _roles_by_name(db, payload.roles)

    user = User(
        code=code_service.next_code(db, "user"),
        email=email,
        employee_code=employee_code,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        designation=payload.designation,
        department=payload.department,
        phone=payload.phone,
        reports_to_id=payload.reports_to_id,
        standard_daily_hours=payload.standard_daily_hours,
        working_days_per_week=payload.working_days_per_week,
    )
    db.add(user)
    db.flush()

    for index, role in enumerate(roles):
        db.add(UserRole(user_id=user.id, role_id=role.id, is_primary=index == 0))
    db.flush()

    audit_service.record(
        db,
        entity_type="user",
        entity_id=user.id,
        entity_code=user.code,
        action=AuditAction.CREATE,
        actor=actor,
        summary=f"Created user {user.full_name} ({', '.join(payload.roles)})",
        context=client_context(request),
    )
    db.refresh(user)
    return UserOut.from_model(user)


@router.get("/users/{user_id}", response_model=UserOut)
def get_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(P.USER_VIEW)),
) -> UserOut:
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found.")
    return UserOut.from_model(user)


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(P.USER_MANAGE)),
) -> UserOut:
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found.")

    tracked = [
        "employee_code", "full_name", "designation", "department", "phone",
        "is_active", "reports_to_id", "standard_daily_hours",
        "working_days_per_week",
    ]
    before = {f: getattr(user, f) for f in tracked}
    before["roles"] = sorted(user.role_names)

    updates = payload.model_dump(exclude_unset=True)
    new_roles = updates.pop("roles", None)

    # Normalised and checked here rather than trusted from the client: an
    # employee code is what someone signs in with, so two accounts sharing one
    # would make a login ambiguous.
    if "employee_code" in updates and updates["employee_code"]:
        code = updates["employee_code"].strip().upper()
        clash = db.execute(
            select(User.id).where(
                User.employee_code == code, User.id != user.id
            )
        ).first()
        if clash:
            raise ValidationError(
                f"Employee code {code} already belongs to another account."
            )
        updates["employee_code"] = code

    for field, value in updates.items():
        setattr(user, field, value)

    if new_roles is not None:
        roles = _roles_by_name(db, new_roles)
        for existing in list(user.roles):
            db.delete(existing)
        db.flush()
        for index, role in enumerate(roles):
            db.add(UserRole(user_id=user.id, role_id=role.id, is_primary=index == 0))

    db.flush()
    db.refresh(user)

    after = {f: getattr(user, f) for f in tracked}
    after["roles"] = sorted(user.role_names)
    audit_service.record_change(
        db,
        entity_type="user",
        entity_id=user.id,
        entity_code=user.code,
        before=before,
        after=after,
        actor=actor,
        context=client_context(request),
    )
    return UserOut.from_model(user)


@router.post("/users/{user_id}/skills", response_model=UserOut)
def set_user_skill(
    user_id: uuid.UUID,
    payload: UserSkillAssign,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(P.SKILL_MANAGE)),
) -> UserOut:
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found.")
    skill = db.get(Skill, payload.skill_id)
    if skill is None:
        raise NotFoundError("Skill not found.")

    existing = db.execute(
        select(UserSkill).where(
            UserSkill.user_id == user.id, UserSkill.skill_id == skill.id
        )
    ).scalar_one_or_none()

    rank = SKILL_LEVEL_RANK[payload.level]
    if existing is None:
        db.add(
            UserSkill(
                user_id=user.id,
                skill_id=skill.id,
                level=payload.level,
                level_rank=rank,
                years_experience=payload.years_experience,
            )
        )
    else:
        existing.level = payload.level
        existing.level_rank = rank
        existing.years_experience = payload.years_experience

    db.flush()
    db.refresh(user)
    return UserOut.from_model(user)


@router.delete("/users/{user_id}/skills/{skill_id}", response_model=Message)
def remove_user_skill(
    user_id: uuid.UUID,
    skill_id: uuid.UUID,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(P.SKILL_MANAGE)),
) -> Message:
    row = db.execute(
        select(UserSkill).where(
            UserSkill.user_id == user_id, UserSkill.skill_id == skill_id
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError("That skill is not assigned to this user.")
    db.delete(row)
    db.flush()
    return Message(message="Skill removed.")


@router.get("/roles", response_model=list[RoleOut])
def list_roles(
    db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> list[RoleOut]:
    rows = db.execute(select(Role).order_by(Role.rank)).scalars().all()
    return [RoleOut.model_validate(r) for r in rows]


@router.get("/skills", response_model=list[SkillOut])
def list_skills(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(P.SKILL_VIEW)),
    active_only: bool = True,
) -> list[SkillOut]:
    stmt = select(Skill)
    if active_only:
        stmt = stmt.where(Skill.is_active.is_(True))
    rows = db.execute(stmt.order_by(Skill.category, Skill.name)).scalars().all()
    return [SkillOut.model_validate(s) for s in rows]


@router.post("/skills", response_model=SkillOut, status_code=201)
def create_skill(
    payload: SkillCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(P.SKILL_MANAGE)),
) -> SkillOut:
    if db.execute(select(Skill.id).where(Skill.name == payload.name)).first():
        raise ValidationError("A skill with that name already exists.")
    skill = Skill(**payload.model_dump())
    db.add(skill)
    db.flush()
    return SkillOut.model_validate(skill)


@router.get("/skills/matrix")
def skill_matrix(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(P.SKILL_VIEW)),
) -> dict:
    """Skill matrix: who has which skill, and at what level."""
    skills = db.execute(select(Skill).where(Skill.is_active.is_(True))).scalars().all()
    users = db.execute(select(User).where(User.is_active.is_(True))).scalars().all()

    levels: dict[str, dict[str, str]] = {}
    for user in users:
        levels[str(user.id)] = {
            str(us.skill_id): us.level for us in user.skills
        }

    return {
        "skills": [
            {"id": str(s.id), "name": s.name, "category": s.category} for s in skills
        ],
        "users": [
            {
                "id": str(u.id),
                "code": u.code,
                "full_name": u.full_name,
                "designation": u.designation,
                "levels": levels.get(str(u.id), {}),
            }
            for u in users
        ],
    }
