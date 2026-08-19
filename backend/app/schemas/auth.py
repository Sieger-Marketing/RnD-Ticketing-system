"""Authentication payloads."""

from __future__ import annotations

import uuid

from pydantic import AliasChoices, BaseModel, Field

from app.schemas.common import ORMModel


class LoginRequest(BaseModel):
    """Sign in with an employee code or an email address.

    Most of the design team signs in as SIES00267; the administrator account
    has an address and no employee code. One field takes either, so the form
    does not make people choose which kind of person they are. The alias keeps
    an older client that posts "email" working unchanged.
    """

    identifier: str = Field(
        min_length=1,
        max_length=255,
        validation_alias=AliasChoices("identifier", "employee_code", "email"),
    )
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
    employee_code: str | None = None
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
            employee_code=user.employee_code,
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
