"""Customer, product family and product payloads."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import ORMModel


class CustomerOut(ORMModel):
    id: uuid.UUID
    code: str
    name: str
    customer_code: str
    industry: str | None = None
    country: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    is_active: bool
    external_id: str | None = None
    created_at: datetime


class CustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    customer_code: str = Field(min_length=1, max_length=40)
    industry: str | None = None
    country: str | None = None
    contact_name: str | None = None
    contact_email: EmailStr | None = None
    contact_phone: str | None = None
    external_id: str | None = None


class CustomerUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    industry: str | None = None
    country: str | None = None
    contact_name: str | None = None
    contact_email: EmailStr | None = None
    contact_phone: str | None = None
    is_active: bool | None = None
    external_id: str | None = None


class ProductFamilyOut(ORMModel):
    id: uuid.UUID
    code: str
    name: str
    description: str | None = None
    is_active: bool


class ProductFamilyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = None


class ProductOut(ORMModel):
    id: uuid.UUID
    code: str
    name: str
    product_family_id: uuid.UUID | None = None
    product_family_name: str | None = None
    description: str | None = None
    is_active: bool
    external_id: str | None = None

    @classmethod
    def from_model(cls, product) -> "ProductOut":
        return cls(
            id=product.id,
            code=product.code,
            name=product.name,
            product_family_id=product.product_family_id,
            product_family_name=product.family.name if product.family else None,
            description=product.description,
            is_active=product.is_active,
            external_id=product.external_id,
        )


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    product_family_id: uuid.UUID | None = None
    description: str | None = None
    external_id: str | None = None


class ProductUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    product_family_id: uuid.UUID | None = None
    description: str | None = None
    is_active: bool | None = None
    external_id: str | None = None


class ReleaseStandardOut(ORMModel):
    """One standard design release, as the design team defined it."""

    id: uuid.UUID
    sequence: int
    name: str
    is_default: bool
    condition: str | None = None
    alternative_name: str | None = None


class StandardVariantOut(BaseModel):
    """A named set of releases -- "standard", or a size-driven alternative."""

    variant: str
    condition: str | None = None
    releases: list[ReleaseStandardOut]


class ProductStandardOut(BaseModel):
    product_id: uuid.UUID
    product_name: str
    #: The five tasks generated under each release, or empty if the shared
    #: template has not been published on this environment.
    tasks: list[str] = []
    variants: list[StandardVariantOut]


class ApplyStandard(BaseModel):
    """Which of a product's standard releases to create on a project."""

    variant: str = "standard"
    release_ids: list[uuid.UUID] = Field(min_length=1)
    generate_tasks: bool = True
    planned_start: date | None = None
