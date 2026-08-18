"""Reference data: customers, product families and products.

These are the entities most likely to be mastered in Salesforce later
(Account -> Customer, Product2 -> Product), so they carry the standard
external-ID columns from day one.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, BusinessEntity

if TYPE_CHECKING:
    from app.models.project import Project


class Customer(Base, BusinessEntity):
    __tablename__ = "customers"

    name: Mapped[str] = mapped_column(String(200), index=True)
    customer_code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    industry: Mapped[str | None] = mapped_column(String(120))
    country: Mapped[str | None] = mapped_column(String(80))
    contact_name: Mapped[str | None] = mapped_column(String(160))
    contact_email: Mapped[str | None] = mapped_column(String(255))
    contact_phone: Mapped[str | None] = mapped_column(String(40))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    projects: Mapped[list["Project"]] = relationship(back_populates="customer")


class ProductFamily(Base, BusinessEntity):
    __tablename__ = "product_families"

    name: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    products: Mapped[list["Product"]] = relationship(back_populates="family")


class Product(Base, BusinessEntity):
    __tablename__ = "products"

    name: Mapped[str] = mapped_column(String(200), index=True)
    product_family_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("product_families.id", ondelete="SET NULL"),
        index=True,
    )
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    family: Mapped[ProductFamily | None] = relationship(
        back_populates="products", lazy="selectin"
    )
    projects: Mapped[list["Project"]] = relationship(back_populates="product")
