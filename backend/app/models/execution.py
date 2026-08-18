"""Execution records: time entries, reviews and revisions.

Every hour the department spends is a TimeEntry row. Efficiency, utilisation,
rework % and cycle time are all derived from these rows plus the task
lifecycle stamps -- there is no second store of "dashboard numbers".
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

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
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import (
    Accountability,
    ReviewStatus,
    RevisionStatus,
    TimeEntrySource,
)
from app.db.base_class import Base, BusinessEntity, Timestamped, UUIDPrimaryKey

if TYPE_CHECKING:
    from app.models.task import Task
    from app.models.user import User


class TimeEntry(Base, BusinessEntity):
    __tablename__ = "time_entries"
    __table_args__ = (
        CheckConstraint("hours >= 0", name="ck_time_entry_hours_non_negative"),
        CheckConstraint(
            "ended_at IS NULL OR started_at IS NULL OR ended_at >= started_at",
            name="ck_time_entry_interval_order",
        ),
        # The workhorse index: every per-person, per-period KPI filters on this.
        Index("ix_time_entries_user_date", "user_id", "entry_date"),
        Index("ix_time_entries_task", "task_id", "entry_date"),
        # At most one running timer per user is enforced in the service layer;
        # this partial-friendly index keeps the lookup cheap.
        Index("ix_time_entries_running", "user_id", "is_running"),
    )

    task_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # Denormalised so period aggregates never need to walk task -> release.
    release_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("design_releases.id", ondelete="CASCADE"),
        index=True,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )

    entry_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    hours: Mapped[float] = mapped_column(Numeric(6, 2), default=0, nullable=False)

    source: Mapped[str] = mapped_column(
        String(20), default=TimeEntrySource.MANUAL.value, nullable=False
    )
    is_running: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # True when logged while the task had an open revision -- this is what
    # makes Rework % measurable rather than estimated.
    is_rework: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    revision_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("revisions.id", ondelete="SET NULL")
    )
    description: Mapped[str | None] = mapped_column(Text)

    task: Mapped["Task"] = relationship(back_populates="time_entries")
    user: Mapped["User"] = relationship(lazy="selectin")


class Review(Base, BusinessEntity):
    __tablename__ = "reviews"
    __table_args__ = (
        Index("ix_reviews_reviewer_status", "reviewer_id", "status"),
        Index("ix_reviews_task_round", "task_id", "round_number"),
    )

    task_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )
    release_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("design_releases.id", ondelete="CASCADE"),
        index=True,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )

    # 1 for the first submission, 2 after the first revision, and so on.
    # First-pass approval % counts approvals where round_number = 1.
    round_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    submitted_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )

    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    review_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Stored rather than computed on read so trend queries stay aggregate-only.
    turnaround_hours: Mapped[float | None] = mapped_column(Numeric(8, 2))

    status: Mapped[str] = mapped_column(
        String(30), default=ReviewStatus.PENDING.value, nullable=False, index=True
    )
    result: Mapped[str | None] = mapped_column(String(30), index=True)
    comments: Mapped[str | None] = mapped_column(Text)

    task: Mapped["Task"] = relationship(back_populates="reviews")
    reviewer: Mapped["User | None"] = relationship(
        foreign_keys=[reviewer_id], lazy="selectin"
    )
    submitted_by: Mapped["User | None"] = relationship(foreign_keys=[submitted_by_id])


class Revision(Base, BusinessEntity):
    """A tracked unit of rework.

    `accountability` separates rework the department caused from rework the
    customer or an upstream input caused. Performance scoring only penalises
    the controllable kind (spec section 16).
    """

    __tablename__ = "revisions"
    __table_args__ = (
        CheckConstraint(
            "additional_hours >= 0", name="ck_revision_hours_non_negative"
        ),
        Index("ix_revisions_status_category", "status", "category"),
        Index("ix_revisions_assignee", "assigned_to_id", "status"),
    )

    task_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )
    release_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("design_releases.id", ondelete="CASCADE"),
        index=True,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    review_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("reviews.id", ondelete="SET NULL")
    )

    revision_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    accountability: Mapped[str] = mapped_column(
        String(20), default=Accountability.CONTROLLABLE.value, nullable=False, index=True
    )
    root_cause: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)

    raised_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    assigned_to_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )

    raised_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    resolved_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Rolled up from time entries flagged is_rework against this revision.
    additional_hours: Mapped[float] = mapped_column(
        Numeric(8, 2), default=0, nullable=False
    )

    status: Mapped[str] = mapped_column(
        String(20), default=RevisionStatus.OPEN.value, nullable=False, index=True
    )

    task: Mapped["Task"] = relationship(back_populates="revisions")
    raised_by: Mapped["User | None"] = relationship(foreign_keys=[raised_by_id])
    assigned_to: Mapped["User | None"] = relationship(
        foreign_keys=[assigned_to_id], lazy="selectin"
    )
