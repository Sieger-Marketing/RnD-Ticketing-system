"""Comments, attachments and notifications.

Comments and attachments are polymorphic over (entity_type, entity_id) so that
projects, releases and tasks all get them without three near-identical tables.
The pair is indexed together because every read is "everything attached to
this one record".
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import NotificationSeverity
from app.db.base_class import Base, BusinessEntity, Timestamped, UUIDPrimaryKey

if TYPE_CHECKING:
    from app.models.user import User


class Comment(Base, UUIDPrimaryKey, Timestamped):
    __tablename__ = "comments"
    __table_args__ = (Index("ix_comments_entity", "entity_type", "entity_id"),)

    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)

    author_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    parent_comment_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("comments.id", ondelete="CASCADE")
    )
    # User IDs referenced with @, resolved to notifications on create.
    mentions: Mapped[list | None] = mapped_column(JSONB, default=list)

    author: Mapped["User | None"] = relationship(lazy="selectin")


class Attachment(Base, BusinessEntity):
    """A stored file.

    `storage_key` is opaque to the application -- the storage adapter decides
    whether it means a path on disk, an S3 key or a Salesforce ContentVersion
    ID. Nothing here assumes local disk (spec section 31).
    """

    __tablename__ = "attachments"
    __table_args__ = (
        CheckConstraint("size_bytes >= 0", name="ck_attachment_size_non_negative"),
        Index("ix_attachments_entity", "entity_type", "entity_id"),
        Index("ix_attachments_version", "entity_type", "entity_id", "file_name",
              "version"),
    )

    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)

    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(160))
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    storage_provider: Mapped[str] = mapped_column(String(30), default="local")
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)

    # Re-uploading the same file name bumps the version and supersedes the
    # previous row rather than replacing it, so history survives.
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )

    uploaded_by: Mapped["User | None"] = relationship(lazy="selectin")


class Notification(Base, UUIDPrimaryKey, Timestamped):
    __tablename__ = "notifications"
    __table_args__ = (
        # The bell query: unread for me, newest first.
        Index("ix_notifications_user_unread", "user_id", "is_read", "created_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # Machine-readable trigger, e.g. task.assigned, release.at_risk.
    event_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(
        String(20), default=NotificationSeverity.INFO.value, nullable=False
    )

    # Deep link target, e.g. ("task", <uuid>) -> /tasks/<uuid>.
    entity_type: Mapped[str | None] = mapped_column(String(40))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))

    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Email is an optional channel behind an abstraction; these track it
    # without coupling the in-app bell to any provider.
    email_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    email_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
