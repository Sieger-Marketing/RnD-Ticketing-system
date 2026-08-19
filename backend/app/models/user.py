"""People, authorisation, skills and capacity.

Authorisation is permission-based rather than role-string-based: routes ask for
a permission code, roles are bags of permissions, and users hold roles. Adding
a role therefore never requires touching route code.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, BusinessEntity, Timestamped, UUIDPrimaryKey


class Permission(Base, UUIDPrimaryKey, Timestamped):
    """A single capability, e.g. `project.create` or `analytics.view_all`."""

    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    module: Mapped[str] = mapped_column(String(40), index=True)
    description: Mapped[str | None] = mapped_column(Text)

    roles: Mapped[list["RolePermission"]] = relationship(
        back_populates="permission", cascade="all, delete-orphan"
    )


class Role(Base, UUIDPrimaryKey, Timestamped):
    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    # Lower ranks see more. Director=10, Manager=20, Lead=30, Designer=40.
    # Used for "can this user act on that user's records" checks.
    rank: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    permissions: Mapped[list["RolePermission"]] = relationship(
        back_populates="role", cascade="all, delete-orphan", lazy="selectin"
    )
    users: Mapped[list["UserRole"]] = relationship(
        back_populates="role", cascade="all, delete-orphan"
    )


class RolePermission(Base, UUIDPrimaryKey):
    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "permission_id"),)

    role_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), index=True
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("permissions.id", ondelete="CASCADE"),
        index=True,
    )

    role: Mapped[Role] = relationship(back_populates="permissions")
    permission: Mapped[Permission] = relationship(
        back_populates="roles", lazy="selectin"
    )


class UserRole(Base, UUIDPrimaryKey, Timestamped):
    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), index=True
    )
    # When a user holds several roles, the primary one decides the landing
    # dashboard after login (spec section 39).
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    user: Mapped["User"] = relationship(back_populates="roles")
    role: Mapped[Role] = relationship(back_populates="users", lazy="selectin")


class User(Base, BusinessEntity):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "standard_daily_hours > 0 AND standard_daily_hours <= 24",
            name="ck_users_daily_hours_range",
        ),
        Index("ix_users_active_email", "is_active", "email"),
    )

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)

    #: What the design team actually calls a person: SIES00267. It is how they
    #: sign in, because it is the identifier already printed on their card and
    #: used on every drawing, and several of them have no work mailbox.
    #: Nullable because the administrator account predates it and has none.
    employee_code: Mapped[str | None] = mapped_column(
        String(40), unique=True, index=True
    )

    hashed_password: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(160))
    designation: Mapped[str | None] = mapped_column(String(120))
    department: Mapped[str | None] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(40))

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Reporting line. A designer points at their team lead, a lead at the
    # design manager. Scopes "my team" queries without a separate table.
    reports_to_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )

    # Capacity baseline. Leave and holidays are subtracted from this to get
    # available hours (spec section 12).
    standard_daily_hours: Mapped[float] = mapped_column(
        Numeric(5, 2), default=8.0, nullable=False
    )
    working_days_per_week: Mapped[int] = mapped_column(
        Integer, default=5, nullable=False
    )

    reports_to: Mapped["User | None"] = relationship(
        remote_side="User.id", back_populates="direct_reports"
    )
    direct_reports: Mapped[list["User"]] = relationship(back_populates="reports_to")
    roles: Mapped[list[UserRole]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
    skills: Mapped[list["UserSkill"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    # -- helpers ----------------------------------------------------------
    @property
    def role_names(self) -> set[str]:
        return {ur.role.name for ur in self.roles if ur.role}

    @property
    def primary_role_name(self) -> str | None:
        for ur in self.roles:
            if ur.is_primary and ur.role:
                return ur.role.name
        return next((ur.role.name for ur in self.roles if ur.role), None)

    @property
    def permission_codes(self) -> set[str]:
        codes: set[str] = set()
        for ur in self.roles:
            if not ur.role:
                continue
            for rp in ur.role.permissions:
                if rp.permission:
                    codes.add(rp.permission.code)
        return codes


class Skill(Base, UUIDPrimaryKey, Timestamped):
    __tablename__ = "skills"

    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    category: Mapped[str | None] = mapped_column(String(80), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    users: Mapped[list["UserSkill"]] = relationship(
        back_populates="skill", cascade="all, delete-orphan"
    )


class UserSkill(Base, UUIDPrimaryKey, Timestamped):
    __tablename__ = "user_skills"
    __table_args__ = (UniqueConstraint("user_id", "skill_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), index=True
    )
    level: Mapped[str] = mapped_column(
        String(20), default="Intermediate", nullable=False
    )
    # 1..4, denormalised from `level` so assignment recommendations can sort
    # and compare without a lookup table join.
    level_rank: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    years_experience: Mapped[float | None] = mapped_column(Numeric(4, 1))

    user: Mapped[User] = relationship(back_populates="skills")
    skill: Mapped[Skill] = relationship(back_populates="users", lazy="selectin")


class UserCapacity(Base, UUIDPrimaryKey, Timestamped):
    """Per-day capacity override.

    Absent a row, the engine falls back to the standard daily hours on working
    days. Rows exist only where reality differs from the baseline.
    """

    __tablename__ = "user_capacity"
    __table_args__ = (
        UniqueConstraint("user_id", "capacity_date"),
        CheckConstraint("available_hours >= 0", name="ck_capacity_non_negative"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    capacity_date: Mapped[date] = mapped_column(Date, index=True)
    available_hours: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)


class LeaveRecord(Base, UUIDPrimaryKey, Timestamped):
    __tablename__ = "leave_records"
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="ck_leave_date_order"),
        CheckConstraint("hours_per_day > 0", name="ck_leave_hours_positive"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    start_date: Mapped[date] = mapped_column(Date, index=True)
    end_date: Mapped[date] = mapped_column(Date, index=True)
    leave_type: Mapped[str] = mapped_column(String(40), default="Planned")
    hours_per_day: Mapped[float] = mapped_column(Numeric(5, 2), default=8.0)
    status: Mapped[str] = mapped_column(String(20), default="Approved", index=True)
    reason: Mapped[str | None] = mapped_column(Text)


class Holiday(Base, UUIDPrimaryKey, Timestamped):
    __tablename__ = "holidays"
    __table_args__ = (UniqueConstraint("holiday_date", "region"),)

    holiday_date: Mapped[date] = mapped_column(Date, index=True)
    name: Mapped[str] = mapped_column(String(120))
    region: Mapped[str] = mapped_column(String(40), default="ALL")
