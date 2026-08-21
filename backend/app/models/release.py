"""Design releases -- the design sequence within a project.

A release is the unit a Team Lead owns end to end: it is generated from a
product template, broken into tasks, executed, reviewed and completed. The
template version it was created from is pinned here so that publishing a new
template version never rewrites history (spec section 9).
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
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import HealthStatus, Priority, ReleaseStatus, ReviewStatus
from app.db.base_class import Base, BusinessEntity

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.task import Task
    from app.models.template import DesignTemplateVersion
    from app.models.user import User


class DesignRelease(Base, BusinessEntity):
    __tablename__ = "design_releases"
    __table_args__ = (
        UniqueConstraint("project_id", "sequence_number", name="uq_release_sequence"),
        CheckConstraint("sequence_number > 0", name="ck_release_sequence_positive"),
        CheckConstraint("estimated_hours >= 0", name="ck_release_estimated_hours"),
        CheckConstraint("actual_hours >= 0", name="ck_release_actual_hours"),
        CheckConstraint(
            "planned_end IS NULL OR planned_start IS NULL OR planned_end >= planned_start",
            name="ck_release_date_order",
        ),
        Index("ix_releases_lead_status", "team_lead_id", "status"),
        Index("ix_releases_project_status", "project_id", "status"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    # Position in the design sequence: DR-001 Concept, DR-002 Mechanical, ...
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(240), index=True)
    release_type: Mapped[str] = mapped_column(String(80), index=True)
    description: Mapped[str | None] = mapped_column(Text)

    product_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL"), index=True
    )
    # Pinned at generation time. Never repointed at a newer version.
    template_version_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("design_template_versions.id", ondelete="SET NULL"),
        index=True,
    )

    team_lead_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    priority: Mapped[str] = mapped_column(
        String(20), default=Priority.MEDIUM.value, nullable=False, index=True
    )

    planned_start: Mapped[date | None] = mapped_column(Date, index=True)
    planned_end: Mapped[date | None] = mapped_column(Date, index=True)
    actual_start: Mapped[date | None] = mapped_column(Date)
    actual_end: Mapped[date | None] = mapped_column(Date)

    #: How many of this system the project takes. A Puzzle project often buys
    #: several identical systems -- "11 UNITS" of one configuration -- and the
    #: same release is designed once and built that many times, so the number
    #: belongs to the release rather than to the project.
    unit_count: Mapped[int | None] = mapped_column(Integer)

    estimated_hours: Mapped[float] = mapped_column(
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

    status: Mapped[str] = mapped_column(
        String(40), default=ReleaseStatus.DRAFT.value, nullable=False, index=True
    )
    review_status: Mapped[str] = mapped_column(
        String(30), default=ReviewStatus.NOT_SUBMITTED.value, nullable=False
    )
    health: Mapped[str] = mapped_column(
        String(10), default=HealthStatus.GREEN.value, nullable=False, index=True
    )
    health_reasons: Mapped[list | None] = mapped_column(JSONB, default=list)

    # Design Sub-Qualities: how many drawings this assembly releases.
    dsq_count: Mapped[int | None] = mapped_column(Integer)
    revision_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    delay_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    delay_reason: Mapped[str | None] = mapped_column(String(80))
    delay_note: Mapped[str | None] = mapped_column(Text)

    #: Why the release was paused, and by whom, so a hold is answerable rather
    #: than something that quietly happened.
    hold_reason: Mapped[str | None] = mapped_column(String(80))
    hold_note: Mapped[str | None] = mapped_column(Text)

    # Set when a manager force-completes a release that still has open
    # mandatory tasks (spec section 42). Presence of a value is the audit flag.
    completion_override_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    completion_override_reason: Mapped[str | None] = mapped_column(Text)

    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    project: Mapped["Project"] = relationship(back_populates="releases")
    team_lead: Mapped["User | None"] = relationship(
        foreign_keys=[team_lead_id], lazy="selectin"
    )
    created_by: Mapped["User | None"] = relationship(foreign_keys=[created_by_id])
    completion_override_by: Mapped["User | None"] = relationship(
        foreign_keys=[completion_override_by_id]
    )
    template_version: Mapped["DesignTemplateVersion | None"] = relationship(
        back_populates="releases"
    )
    tasks: Mapped[list["Task"]] = relationship(
        back_populates="release", cascade="all, delete-orphan"
    )
