"""Customer, product family and product endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_permission
from app.core.errors import NotFoundError, ValidationError
from app.core.permissions import P
from app.db.session import get_db
from app.models.catalog import Customer, Product, ProductFamily
from app.models.user import User
from app.schemas.catalog import (
    CustomerCreate,
    CustomerOut,
    CustomerUpdate,
    ProductCreate,
    ProductFamilyCreate,
    ProductFamilyOut,
    ProductOut,
    ProductUpdate,
)
from app.schemas.common import Page
from app.services import code_service

router = APIRouter(tags=["catalog"])


@router.get("/customers", response_model=Page[CustomerOut])
def list_customers(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    active_only: bool = True,
    search: str | None = None,
) -> Page[CustomerOut]:
    stmt = select(Customer)
    if active_only:
        stmt = stmt.where(Customer.is_active.is_(True))
    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(Customer.name.ilike(pattern), Customer.customer_code.ilike(pattern))
        )

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar() or 0
    rows = (
        db.execute(
            stmt.order_by(Customer.name)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    return Page.build(
        [CustomerOut.model_validate(c) for c in rows], total, page, page_size
    )


@router.post("/customers", response_model=CustomerOut, status_code=201)
def create_customer(
    payload: CustomerCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(P.PROJECT_CREATE)),
) -> CustomerOut:
    if db.execute(
        select(Customer.id).where(Customer.customer_code == payload.customer_code)
    ).first():
        raise ValidationError("That customer code is already in use.")

    customer = Customer(code=code_service.next_code(db, "customer"), **payload.model_dump())
    db.add(customer)
    db.flush()
    return CustomerOut.model_validate(customer)


@router.patch("/customers/{customer_id}", response_model=CustomerOut)
def update_customer(
    customer_id: uuid.UUID,
    payload: CustomerUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(P.PROJECT_UPDATE)),
) -> CustomerOut:
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise NotFoundError("Customer not found.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(customer, field, value)
    db.flush()
    return CustomerOut.model_validate(customer)


@router.get("/product-families", response_model=list[ProductFamilyOut])
def list_families(
    db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> list[ProductFamilyOut]:
    rows = (
        db.execute(
            select(ProductFamily)
            .where(ProductFamily.is_active.is_(True))
            .order_by(ProductFamily.name)
        )
        .scalars()
        .all()
    )
    return [ProductFamilyOut.model_validate(f) for f in rows]


@router.post("/product-families", response_model=ProductFamilyOut, status_code=201)
def create_family(
    payload: ProductFamilyCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(P.SETTINGS_MANAGE)),
) -> ProductFamilyOut:
    if db.execute(
        select(ProductFamily.id).where(ProductFamily.name == payload.name)
    ).first():
        raise ValidationError("A product family with that name already exists.")
    family = ProductFamily(
        code=code_service.next_code(db, "product_family"), **payload.model_dump()
    )
    db.add(family)
    db.flush()
    return ProductFamilyOut.model_validate(family)


@router.get("/products", response_model=list[ProductOut])
def list_products(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    product_family_id: uuid.UUID | None = None,
    active_only: bool = True,
) -> list[ProductOut]:
    stmt = select(Product)
    if product_family_id:
        stmt = stmt.where(Product.product_family_id == product_family_id)
    if active_only:
        stmt = stmt.where(Product.is_active.is_(True))
    rows = db.execute(stmt.order_by(Product.name)).scalars().all()
    return [ProductOut.from_model(p) for p in rows]


@router.post("/products", response_model=ProductOut, status_code=201)
def create_product(
    payload: ProductCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(P.SETTINGS_MANAGE)),
) -> ProductOut:
    product = Product(code=code_service.next_code(db, "product"), **payload.model_dump())
    db.add(product)
    db.flush()
    db.refresh(product)
    return ProductOut.from_model(product)


@router.patch("/products/{product_id}", response_model=ProductOut)
def update_product(
    product_id: uuid.UUID,
    payload: ProductUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(P.SETTINGS_MANAGE)),
) -> ProductOut:
    product = db.get(Product, product_id)
    if product is None:
        raise NotFoundError("Product not found.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
    db.flush()
    db.refresh(product)
    return ProductOut.from_model(product)
