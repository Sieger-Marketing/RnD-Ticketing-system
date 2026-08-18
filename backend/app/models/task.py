"""Tasks -- the smallest execution unit -- and their dependencies.

Two things here exist specifically for the AI-readiness requirement (section
50): `original_estimated_hours` is written once and never touched again, and
every subsequent re-estimate appends a TaskEstimateHistory row. Historical
estimates are therefore never overwritten, which is what makes duration and
effort prediction trainable later.
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
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import DependencyType, Priority, ReviewStatus, TaskStatus
from app.db.base_class import Base, BusinessEntity, Timestamped, UUIDPrimaryKey

if TYPE_CHECKING:
    from app.models.execution import Review, Revision, TimeEntry
    from app.models.project import Project
    from app.models.release import DesignRelease
    from app.models.user import Skill, User


class Task(Base, BusinessEntity):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint("estimated_hours >= 0", name="ck_task_estimated_non_negative"),
        CheckConstraint("actual_hours >= 0", name="ck_task_actual_non_negative"),
        CheckConstraint("rework_hours >= 0", name="ck_task_rework_non_negative"),
        CheckConstraint(
            "completion_percent >= 0 AND completion_percent <= 100",
            name="ck_task_completion_range",
        ),
        CheckConstraint(
            "planned_end IS NULL OR planned_start IS NULL OR planned_end >= planned_start",
            name="ck_task_date_order",
        ),
        CheckConstraint("complexity BETWEEN 1 AND 5", name="ck_task_complexity_range"),
        Index("ix_tasks_assignee_status", "assigned_to_id", "status"),
        Index("ix_tasks_release_status", "release_id", "status"),
        Index("ix_tasks_due", "status", "planned_end"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    release_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("design_releases.id", ondelete="CASCADE"),
        index=True,
    )
    parent_task_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"), index=True
    )
    # Which template row produced this task, NULL for manually added ones.
    # Lets the analytics layer compare planned-vs-actual per standard step.
    template_task_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("template_tasks.id", ondelete="SET NULL")
    )

    name: Mapped[str] = mapped_column(String(240), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    task_type: Mapped[str] = mapped_column(String(80), index=True)
    sequence: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    assigned_to_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    team_lead_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    required_skill_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("skills.id", ondelete="SET NULL"), index=True
    )

    priority: Mapped[str] = mapped_column(
        String(20), default=Priority.MEDIUM.value, nullable=False, index=True
    )
    # 1 (trivial) .. 5 (very complex). Weights the performance score.
    complexity: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    is_mandatory: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    requires_review: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    planned_start: Mapped[date | None] = mapped_column(Date, index=True)
    planned_end: Mapped[date | None] = mapped_column(Date, index=True)

    # Written once at creation and never modified; re-estimates go to
    # estimate_history. This is the baseline every variance is measured from.
    original_estimated_hours: Mapped[float] = mapped_column(
        Numeric(8, 2), default=0, nullable=False
    )
    estimated_hours: Mapped[float] = mapped_column(
        Numeric(8, 2), default=0, nullable=False
    )
    actual_hours: Mapped[float] = mapped_column(
        Numeric(8, 2), default=0, nullable=False
    )
    # Hours logged against this task while a revision was open. Feeds Rework %.
    rework_hours: Mapped[float] = mapped_column(
        Numeric(8, 2), default=0, nullable=False
    )
    blocked_hours: Mapped[float] = mapped_column(
        Numeric(8, 2), default=0, nullable=False
    )

    status: Mapped[str] = mapped_column(
        String(40), default=TaskStatus.NOT_STARTED.value, nullable=False, index=True
    )
    completion_percent: Mapped[float] = mapped_column(
        Numeric(5, 2), default=0, nullable=False
    )
    review_status: Mapped[str] = mapped_column(
        String(30), default=ReviewStatus.NOT_SUBMITTED.value, nullable=False, index=True
    )
    revision_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    submission_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    blocker_reason: Mapped[str | None] = mapped_column(Text)
    blocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delay_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    delay_reason: Mapped[str | None] = mapped_column(String(80), index=True)
    delay_note: Mapped[str | None] = mapped_column(Text)

    # Lifecycle stamps. Cycle time = completed_at - started_at, queue time =
    # started_at - assigned_at (spec section 45).
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )

    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    project: Mapped["Project"] = relationship()
    release: Mapped["DesignRelease"] = relationship(back_populates="tasks")
    assigned_to: Mapped["User | None"] = relationship(
        foreign_keys=[assigned_to_id], lazy="selectin"
    )
    team_lead: Mapped["User | None"] = relationship(foreign_keys=[team_lead_id])
    created_by: Mapped["User | None"] = relationship(foreign_keys=[created_by_id])
    required_skill: Mapped["Skill | None"] = relationship(lazy="selectin")

    time_entries: Mapped[list["TimeEntry"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    reviews: Mapped[list["Review"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    revisions: Mapped[list["Revision"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    estimate_history: Mapped[list["TaskEstimateHistory"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )

    # Dependency edges. `prerequisites` are tasks this one waits for.
    prerequisites: Mapped[list["TaskDependency"]] = relationship(
        foreign_keys="TaskDependency.task_id",
        back_populates="task",
        cascade="all, delete-orphan",
    )
    dependents: Mapped[list["TaskDependency"]] = relationship(
        foreign_keys="TaskDependency.depends_on_task_id",
        back_populates="depends_on_task",
        cascade="all, delete-orphan",
    )

    @property
    def effort_weight(self) -> float:
        """Relative weight of this task for effort-normalised scoring."""
        from app.core.enums import PRIORITY_WEIGHT

        hours = float(self.original_estimated_hours or self.estimated_hours or 0)
        return max(hours, 0.5) * (1 + (self.complexity - 3) * 0.15) * PRIORITY_WEIGHT.get(
            self.priority, 1.0
        )


class TaskDependency(Base, UUIDPrimaryKey, Timestamped):
    """`task_id` cannot proceed until `depends_on_task_id` is satisfied."""

    __tablename__ = "task_dependencies"
    __table_args__ = (
        UniqueConstraint("task_id", "depends_on_task_id", name="uq_task_dependency"),
        CheckConstraint("task_id <> depends_on_task_id", name="ck_no_self_dependency"),
    )

    task_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )
    depends_on_task_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )
    dependency_type: Mapped[str] = mapped_column(
        String(30), default=DependencyType.FINISH_TO_START.value, nullable=False
    )
    # A soft dependency warns but does not block execution.
    is_blocking: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    task: Mapped[Task] = relationship(
        foreign_keys=[task_id], back_populates="prerequisites"
    )
    depends_on_task: Mapped[Task] = relationship(
        foreign_keys=[depends_on_task_id], back_populates="dependents", lazy="selectin"
    )


class TaskEstimateHistory(Base, UUIDPrimaryKey, Timestamped):
    """Append-only log of every estimate change on a task.

    Exists so that re-estimating never destroys the prior number -- the
    original plan stays auditable and the series stays usable as training data.
    """

    __tablename__ = "task_estimate_history"

    task_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )
    previous_hours: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    new_hours: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    changed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    task: Mapped[Task] = relationship(back_populates="estimate_history")
