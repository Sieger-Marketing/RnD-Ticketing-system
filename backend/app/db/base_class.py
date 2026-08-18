"""Declarative base and the mixins every business entity shares.

Spec section 3 requires each major entity to carry an internal UUID, a
human-readable identifier, an external ID for future Salesforce
synchronisation, and creation/update timestamps. Putting that in one mixin
keeps every table consistent and keeps the integration layer generic.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UUIDPrimaryKey:
    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


class Timestamped:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ExternallyIdentified:
    """Human-readable code plus a slot for the ID an external system knows.

    `code` is what people type and quote in meetings (PRJ-0007, DR-0031,
    TSK-01042). `external_id` and `external_system` stay NULL until an adapter
    claims the record, so nothing in core business logic depends on Salesforce
    being present.
    """

    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    external_id: Mapped[str | None] = mapped_column(String(80), index=True)
    external_system: Mapped[str | None] = mapped_column(String(40))


class BusinessEntity(UUIDPrimaryKey, ExternallyIdentified, Timestamped):
    """Convenience combination used by the major transactional entities."""
