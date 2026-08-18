"""Authentication payloads."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import ORMModel


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: "CurrentUser"


class CurrentUser(ORMModel):
    id: uuid.UUID
    code: str
    email: str
    full_name: str
    designation: str | None = None
    department: str | None = None
    roles: list[str] = []
    primary_role: str | None = None
    permissions: list[str] = []
    home_route: str = "/"

    @classmethod
    def from_user(cls, user, home_route: str) -> "CurrentUser":
        return cls(
            id=user.id,
            code=user.code,
            email=user.email,
            full_name=user.full_name,
            designation=user.designation,
            department=user.department,
            roles=sorted(user.role_names),
            primary_role=user.primary_role_name,
            permissions=sorted(user.permission_codes),
            home_route=home_route,
        )


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


TokenResponse.model_rebuild()
