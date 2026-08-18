"""Cross-cutting infrastructure tables.

Configuration, audit trail, status history, human-readable ID counters and the
Salesforce-ready integration bookkeeping all live here. None of the core
business services import a vendor SDK -- they only ever touch these tables.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
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

from app.core.enums import SyncDirection, SyncStatus
from app.db.base_class import Base, Timestamped, UUIDPrimaryKey

if TYPE_CHECKING:
    from app.models.user import User


class AppSetting(Base, UUIDPrimaryKey, Timestamped):
    """Runtime-tunable business rules.

    Capacity thresholds, KPI weights, delay reasons, revision categories,
    working hours and health rules all live here so that section 34's "avoid
    hard-coding configurable business rules" holds. Values are JSON so a
    setting can be a number, a list or an object.
    """

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    category: Mapped[str] = mapped_column(String(60), index=True)
    value: Mapped[dict | list | None] = mapped_column(JSONB, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # System settings are required by the engines; deleting them is refused.
    is_system: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )


class DocumentCounter(Base, UUIDPrimaryKey, Timestamped):
    """Allocates the human-readable codes (PRJ-0007, DR-0031, TSK-01042).

    A row per entity prefix, incremented under a row lock so concurrent
    creates cannot collide. Kept in the database rather than derived from a
    count so that deletions never cause a code to be reused.
    """

    __tablename__ = "document_counters"

    entity: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    prefix: Mapped[str] = mapped_column(String(10), nullable=False)
    padding: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    last_value: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class StatusHistory(Base, UUIDPrimaryKey, Timestamped):
    """Every status transition of every workflow entity.

    Separate from audit_logs because it is queried as a time series (cycle
    time, time-in-status, bottleneck analysis) rather than browsed as a log.
    """

    __tablename__ = "status_history"
    __table_args__ = (
        Index("ix_status_history_entity", "entity_type", "entity_id", "changed_at"),
    )

    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)

    from_status: Mapped[str | None] = mapped_column(String(40))
    to_status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    # Hours the entity spent in `from_status`, computed on write so bottleneck
    # queries are a plain aggregate.
    duration_hours: Mapped[float | None] = mapped_column(Numeric(10, 2))

    changed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    note: Mapped[str | None] = mapped_column(Text)


class AuditLog(Base, UUIDPrimaryKey, Timestamped):
    """Append-only record of who changed what.

    `old_value`/`new_value` hold only the fields that actually changed, so the
    log stays readable and important history is never silently overwritten
    (spec section 30).
    """

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_entity", "entity_type", "entity_id", "created_at"),
        Index("ix_audit_actor", "actor_id", "created_at"),
    )

    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    entity_code: Mapped[str | None] = mapped_column(String(40), index=True)

    action: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    summary: Mapped[str | None] = mapped_column(Text)
    old_value: Mapped[dict | None] = mapped_column(JSONB)
    new_value: Mapped[dict | None] = mapped_column(JSONB)

    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    actor_email: Mapped[str | None] = mapped_column(String(255))
    ip_address: Mapped[str | None] = mapped_column(String(60))
    user_agent: Mapped[str | None] = mapped_column(String(400))

    actor: Mapped["User | None"] = relationship(lazy="selectin")


class IntegrationRecord(Base, UUIDPrimaryKey, Timestamped):
    """Maps an internal record to its counterpart in an external system.

    Deliberately generic: `external_system` is a string, not a Salesforce flag.
    A second adapter (ERP, PLM) needs no schema change (spec section 37).
    """

    __tablename__ = "integration_records"
    __table_args__ = (
        UniqueConstraint(
            "external_system",
            "entity_type",
            "internal_id",
            name="uq_integration_internal",
        ),
        Index(
            "ix_integration_external",
            "external_system",
            "entity_type",
            "external_object_id",
        ),
    )

    external_system: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    internal_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    external_object_id: Mapped[str | None] = mapped_column(String(120))
    external_object_type: Mapped[str | None] = mapped_column(String(80))

    direction: Mapped[str] = mapped_column(
        String(20), default=SyncDirection.BIDIRECTIONAL.value, nullable=False
    )
    sync_status: Mapped[str] = mapped_column(
        String(20), default=SyncStatus.PENDING.value, nullable=False, index=True
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sync_error: Mapped[str | None] = mapped_column(Text)
    payload_hash: Mapped[str | None] = mapped_column(String(64))


class SyncLog(Base, UUIDPrimaryKey, Timestamped):
    __tablename__ = "sync_logs"
    __table_args__ = (Index("ix_sync_logs_system_time", "external_system", "started_at"),)

    external_system: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(40))
    direction: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    records_processed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    message: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict | None] = mapped_column(JSONB)
