"""Authentication endpoints."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import client_context, get_current_user
from app.core.enums import AuditAction
from app.core.errors import AuthenticationError
from app.core.permissions import ROLE_HOME_ROUTE
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest,
    CurrentUser,
    LoginRequest,
    TokenResponse,
)
from app.schemas.common import Message
from app.services import audit_service

router = APIRouter(prefix="/auth", tags=["auth"])


def home_route_for(user: User) -> str:
    return ROLE_HOME_ROUTE.get(user.primary_role_name or "", "/")


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest, request: Request, db: Session = Depends(get_db)
) -> TokenResponse:
    identifier = payload.identifier.strip()

    # Either identity, matched in one query. Employee codes are compared
    # case-insensitively because people type sies00267 as readily as SIES00267,
    # and a code is not a secret worth being fussy about.
    user = db.execute(
        select(User).where(
            or_(
                User.email == identifier.lower(),
                func.upper(User.employee_code) == identifier.upper(),
            )
        )
    ).scalar_one_or_none()

    # Same message and roughly the same work whether the identifier is unknown
    # or the password is wrong, so the endpoint does not confirm which accounts
    # exist.
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise AuthenticationError("Incorrect employee code or password.")
    if not user.is_active:
        raise AuthenticationError("This account has been deactivated.")

    user.last_login_at = datetime.now(UTC)
    audit_service.record(
        db,
        entity_type="user",
        entity_id=user.id,
        entity_code=user.code,
        action=AuditAction.LOGIN,
        actor=user,
        summary="Signed in",
        context=client_context(request),
    )

    token = create_access_token(
        user.id,
        extra_claims={
            "email": user.email,
            "roles": sorted(user.role_names),
        },
    )
    return TokenResponse(
        access_token=token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=CurrentUser.from_user(user, home_route_for(user)),
    )


@router.get("/me", response_model=CurrentUser)
def me(user: User = Depends(get_current_user)) -> CurrentUser:
    return CurrentUser.from_user(user, home_route_for(user))


@router.post("/change-password", response_model=Message)
def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Message:
    if not verify_password(payload.current_password, user.hashed_password):
        raise AuthenticationError("Your current password is incorrect.")

    user.hashed_password = hash_password(payload.new_password)
    audit_service.record(
        db,
        entity_type="user",
        entity_id=user.id,
        entity_code=user.code,
        action=AuditAction.UPDATE,
        actor=user,
        summary="Changed password",
        context=client_context(request),
    )
    return Message(message="Password updated.")
