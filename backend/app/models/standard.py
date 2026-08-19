"""The standard design releases a product produces (the DSQ list).

The existing template engine standardises the *tasks inside* a release. This
is the level above it: which releases a product should produce at all.

Kept as its own table rather than as forty-one templates, because the releases
of a product are a list that changes together -- adding a sixth Tower DSQ is
one decision about Tower, not the creation of an unrelated template. The tasks
are shared: every release, on every product, runs the same five.

Some entries are conditional. A Puzzle produces four releases but has five
defined, because Foundation applies above three levels and Ceiling Supports at
two -- never both. The condition travels with the row so a manager is shown
the rule rather than a bare checkbox.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, Timestamped, UUIDPrimaryKey


class ReleaseStandard(Base, UUIDPrimaryKey, Timestamped):
    """One standard design release for a product."""

    __tablename__ = "release_standards"
    __table_args__ = (
        UniqueConstraint("product_id", "variant", "sequence", name="uq_standard_order"),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), index=True
    )

    #: Which set this row belongs to. A Stacker of ten units or fewer releases
    #: as a single combined DSQ instead of three, so the same product carries
    #: two named sets rather than one set with an exception buried in it.
    variant: Mapped[str] = mapped_column(String(60), default="standard", nullable=False)
    variant_condition: Mapped[str | None] = mapped_column(Text)

    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    #: True for releases every project of this product gets. False means the
    #: manager is asked, with `condition` explaining when it applies.
    is_default: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    condition: Mapped[str | None] = mapped_column(Text)

    #: Where the same slot is filled by a different release depending on site
    #: conditions -- Ceiling Supports, or Top Support where there is no ceiling.
    alternative_name: Mapped[str | None] = mapped_column(String(200))

    product = relationship("Product", lazy="joined")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<ReleaseStandard {self.sequence}. {self.name}>"
