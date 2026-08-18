"""Shared schema building blocks."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class EntityRef(ORMModel):
    """Minimal reference to a related record.

    Lists embed these instead of full objects: a task list needs the
    assignee's name, not their capacity settings, and sending the whole user
    would multiply payload size for no benefit.
    """

    id: uuid.UUID
    code: str | None = None
    name: str | None = None


class Page(BaseModel, Generic[T]):
    """Envelope for every list endpoint (spec section 36)."""

    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int

    @classmethod
    def build(cls, items: list[T], total: int, page: int, page_size: int) -> "Page[T]":
        pages = (total + page_size - 1) // page_size if page_size else 0
        return cls(
            items=items, total=total, page=page, page_size=page_size, pages=pages
        )


class PaginationParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(25, ge=1, le=200)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class Message(BaseModel):
    message: str


class TimestampMixin(BaseModel):
    created_at: datetime
    updated_at: datetime
