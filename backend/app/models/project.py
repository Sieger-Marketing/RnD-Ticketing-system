"""Design projects and their membership.

Rolled-up numbers (actual hours, completion %, health) are stored columns kept
current by app/services/rollup_service.py rather than recomputed on every read.
They are always derived from transactional rows -- never entered by hand -- so
dashboards stay fast without becoming a second source of truth.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import HealthStatus, Priority, ProjectStatus
from app.db.base_class import Base, BusinessEntity, Timestamped, UUIDPrimaryKey

if TYPE_CHECKING:
    from app.models.catalog import Customer, Product
    from app.models.release import DesignRelease
    from app.models.user import User


class Project(Base, BusinessEntity):
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint("planned_hours >= 0", name="ck_project_planned_hours"),
        CheckConstraint("actual_hours >= 0", name="ck_project_actual_hours"),
        CheckConstraint(
            "required_completion_date IS NULL OR start_date IS NULL "
            "OR required_completion_date >= start_date",
            name="ck_project_date_order",
        ),
        Index("ix_projects_status_health", "status", "health"),
        Index("ix_projects_manager_status", "design_manager_id", "status"),
        Index("ix_projects_lead_status", "team_lead_id", "status"),
    )

    name: Mapped[str] = mapped_column(String(240), index=True)
    description: Mapped[str | None] = mapped_column(Text)

    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), index=True
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL"), index=True
    )

    project_type: Mapped[str | None] = mapped_column(String(80), index=True)
    # Commercial references. Free text today; these become the Salesforce
    # Sales Order / Work Order links once an adapter is wired up.
    # Bay capacity of the system being designed. The design team plan around
    # it, so it belongs on the project rather than in a description.
    car_count: Mapped[int | None] = mapped_column(Integer)
    # Good For Construction: the date the design is frozen for manufacture.
    gfc_date: Mapped[date | None] = mapped_column(Date)
    sales_order: Mapped[str | None] = mapped_column(String(80), index=True)
    work_order: Mapped[str | None] = mapped_column(String(80), index=True)

    project_manager_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    design_manager_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    #: The team lead accountable for running this project's design work.
    #: Releases and tasks already carry one; a project did not, so a lead could
    #: only be attributed to a project indirectly -- by walking down to a
    #: release they happened to lead. That fails for a project whose releases
    #: do not exist yet, which is precisely when somebody needs to own it.
    team_lead_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )

    priority: Mapped[str] = mapped_column(
        String(20), default=Priority.MEDIUM.value, nullable=False, index=True
    )

    start_date: Mapped[date | None] = mapped_column(Date, index=True)
    required_completion_date: Mapped[date | None] = mapped_column(Date, index=True)
    internal_deadline: Mapped[date | None] = mapped_column(Date)
    customer_deadline: Mapped[date | None] = mapped_column(Date)
    actual_completion_date: Mapped[date | None] = mapped_column(Date)

    #: When the project is currently expected to finish: the latest forecast
    #: among the releases that gate its completion. Derived, never typed.
    #: Compared against required_completion_date, this is the one number that
    #: answers "will we make it", which nothing in the system could answer.
    forecast_end: Mapped[date | None] = mapped_column(Date, index=True)

    planned_hours: Mapped[float] = mapped_column(
        Numeric(10, 2), default=0, nullable=False
    )
    actual_hours: Mapped[float] = mapped_column(
        Numeric(10, 2), default=0, nullable=False
    )
    rework_hours: Mapped[float] = mapped_column(
        Numeric(10, 2), default=0, nullable=False
    )

    completion_percent: Mapped[float] = mapped_column(
        Numeric(5, 2), default=0, nullable=False
    )
    revision_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    delay_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    status: Mapped[str] = mapped_column(
        String(40), default=ProjectStatus.NOT_STARTED.value, nullable=False, index=True
    )
    health: Mapped[str] = mapped_column(
        String(10), default=HealthStatus.GREEN.value, nullable=False, index=True
    )
    # Why the health engine landed on amber/red. Spec section 21 requires the
    # reasons to be visible, not just the colour.
    health_reasons: Mapped[list | None] = mapped_column(JSONB, default=list)

    #: Why the project was paused. A held project still accrues delay against
    #: its required date -- pausing the work does not move the customer's
    #: deadline -- so the reason is what explains the colour.
    hold_reason: Mapped[str | None] = mapped_column(String(80))
    hold_note: Mapped[str | None] = mapped_column(Text)

    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    customer: Mapped["Customer | None"] = relationship(
        back_populates="projects", lazy="selectin"
    )
    product: Mapped["Product | None"] = relationship(
        back_populates="projects", lazy="selectin"
    )
    design_manager: Mapped["User | None"] = relationship(
        foreign_keys=[design_manager_id], lazy="selectin"
    )
    project_manager: Mapped["User | None"] = relationship(
        foreign_keys=[project_manager_id], lazy="selectin"
    )
    team_lead: Mapped["User | None"] = relationship(
        foreign_keys=[team_lead_id], lazy="selectin"
    )
    created_by: Mapped["User | None"] = relationship(foreign_keys=[created_by_id])

    releases: Mapped[list["DesignRelease"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    members: Mapped[list["ProjectMember"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class ProjectMember(Base, UUIDPrimaryKey, Timestamped):
    __tablename__ = "project_members"
    __table_args__ = (
        Index("ix_project_members_unique", "project_id", "user_id", unique=True),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    project_role: Mapped[str] = mapped_column(String(60), default="Contributor")

    project: Mapped[Project] = relationship(back_populates="members")
    user: Mapped["User"] = relationship(lazy="selectin")
