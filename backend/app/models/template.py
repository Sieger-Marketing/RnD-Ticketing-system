"""Product-based design templates (spec section 9).

Three levels:

    DesignTemplate          identity -- "Mechanical Design for APS"
      DesignTemplateVersion   an immutable published snapshot -- v1, v2, v3
        TemplateTask            the standard tasks in that snapshot

Releases pin a version, so republishing never mutates work already generated.
Only a draft version is editable; publishing freezes it.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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

from app.core.enums import Priority
from app.db.base_class import Base, BusinessEntity, Timestamped, UUIDPrimaryKey

if TYPE_CHECKING:
    from app.models.catalog import Product, ProductFamily
    from app.models.release import DesignRelease
    from app.models.user import User


class DesignTemplate(Base, BusinessEntity):
    """The template identity. Versions hang off it."""

    __tablename__ = "design_templates"
    __table_args__ = (
        Index("ix_templates_match", "product_id", "product_family_id", "release_type"),
    )

    name: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[str | None] = mapped_column(Text)

    # A template matches on product first, then falls back to product family,
    # so a family-wide default covers products with no specific template.
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    product_family_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("product_families.id", ondelete="CASCADE"),
        index=True,
    )
    release_type: Mapped[str] = mapped_column(String(80), index=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    product: Mapped["Product | None"] = relationship(lazy="selectin")
    product_family: Mapped["ProductFamily | None"] = relationship(lazy="selectin")
    versions: Mapped[list["DesignTemplateVersion"]] = relationship(
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="DesignTemplateVersion.version_number",
    )

    @property
    def current_version(self) -> "DesignTemplateVersion | None":
        published = [v for v in self.versions if v.is_published]
        return max(published, key=lambda v: v.version_number, default=None)


class DesignTemplateVersion(Base, UUIDPrimaryKey, Timestamped):
    __tablename__ = "design_template_versions"
    __table_args__ = (
        UniqueConstraint("template_id", "version_number", name="uq_template_version"),
        CheckConstraint("version_number > 0", name="ck_template_version_positive"),
    )

    template_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("design_templates.id", ondelete="CASCADE"),
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    # Frozen once published. Edits require a new draft version.
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    change_note: Mapped[str | None] = mapped_column(Text)

    template: Mapped[DesignTemplate] = relationship(back_populates="versions")
    tasks: Mapped[list["TemplateTask"]] = relationship(
        back_populates="version",
        cascade="all, delete-orphan",
        order_by="TemplateTask.sequence",
        lazy="selectin",
    )
    releases: Mapped[list["DesignRelease"]] = relationship(
        back_populates="template_version"
    )

    @property
    def label(self) -> str:
        return f"v{self.version_number}"


class TemplateTask(Base, UUIDPrimaryKey, Timestamped):
    """A standard task inside a template version."""

    __tablename__ = "template_tasks"
    __table_args__ = (
        UniqueConstraint("version_id", "sequence", name="uq_template_task_sequence"),
        CheckConstraint(
            "default_estimated_hours >= 0", name="ck_template_task_hours_non_negative"
        ),
    )

    version_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("design_template_versions.id", ondelete="CASCADE"),
        index=True,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(240))
    task_type: Mapped[str] = mapped_column(String(80), index=True)
    description: Mapped[str | None] = mapped_column(Text)

    default_estimated_hours: Mapped[float] = mapped_column(
        Numeric(8, 2), default=0, nullable=False
    )
    default_priority: Mapped[str] = mapped_column(
        String(20), default=Priority.MEDIUM.value, nullable=False
    )
    # Relative difficulty, feeding the effort-weighted performance score so a
    # 20-hour complex task is not scored like five 2-hour ones (section 48).
    complexity: Mapped[int] = mapped_column(Integer, default=3, nullable=False)

    required_skill_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("skills.id", ondelete="SET NULL"), index=True
    )
    is_mandatory: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    requires_review: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Sequence number of the task this one waits on, within the same template.
    # Resolved into real TaskDependency rows at generation time.
    depends_on_sequence: Mapped[int | None] = mapped_column(Integer)

    version: Mapped[DesignTemplateVersion] = relationship(back_populates="tasks")
