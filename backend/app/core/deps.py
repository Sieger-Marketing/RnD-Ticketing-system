"""Shared FastAPI dependencies: current user, permission gates, data scoping."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import AuthenticationError, PermissionDeniedError
from app.core.permissions import P, ROLE_RANKS
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User

# auto_error=False so a missing header produces our error envelope rather than
# FastAPI's bare {"detail": ...}.
bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or not credentials.credentials:
        raise AuthenticationError("Authentication required.")

    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise AuthenticationError("Invalid or expired token.")

    try:
        user_id = uuid.UUID(str(payload.get("sub")))
    except (TypeError, ValueError):
        raise AuthenticationError("Invalid token subject.") from None

    # Re-read the user rather than trusting the token's claims. A deactivated
    # account or a revoked role therefore takes effect immediately instead of
    # lasting until the token expires.
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("Account is inactive or no longer exists.")
    return user


def require_permission(*codes: str) -> Callable[..., User]:
    """Dependency factory: caller must hold *every* listed permission."""

    def _guard(user: User = Depends(get_current_user)) -> User:
        held = user.permission_codes
        missing = [c for c in codes if c not in held]
        if missing:
            raise PermissionDeniedError(
                "You do not have permission to perform this action.",
                details={"required": list(codes), "missing": missing},
            )
        return user

    return _guard


def require_any_permission(*codes: str) -> Callable[..., User]:
    """Dependency factory: caller must hold at least one listed permission."""

    def _guard(user: User = Depends(get_current_user)) -> User:
        if not (set(codes) & user.permission_codes):
            raise PermissionDeniedError(
                "You do not have permission to perform this action.",
                details={"required_any": list(codes)},
            )
        return user

    return _guard


class AccessScope:
    """How much of the department a user is allowed to see.

    Routes use this instead of re-deriving visibility rules: a Director or
    Manager sees everything, a Team Lead sees their own reports, a Designer
    sees only their own records.
    """

    def __init__(self, user: User, db: Session) -> None:
        self.user = user
        self.db = db
        self.permissions = user.permission_codes

    @property
    def rank(self) -> int:
        return min(
            (ROLE_RANKS.get(name, 99) for name in self.user.role_names), default=99
        )

    @property
    def sees_everything(self) -> bool:
        return P.TASK_VIEW_ALL in self.permissions or P.PROJECT_VIEW_ALL in self.permissions

    @property
    def sees_team(self) -> bool:
        return P.TASK_VIEW_TEAM in self.permissions

    def visible_user_ids(self) -> set[uuid.UUID] | None:
        """User IDs whose work this user may see. None means "no limit"."""
        if self.sees_everything:
            return None
        if self.sees_team:
            reports = {u.id for u in self.user.direct_reports}
            return reports | {self.user.id}
        return {self.user.id}

    def assert_can_view_user(self, target_id: uuid.UUID) -> None:
        allowed = self.visible_user_ids()
        if allowed is not None and target_id not in allowed:
            raise PermissionDeniedError("You cannot view this user's records.")


def get_scope(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> AccessScope:
    return AccessScope(user, db)


def client_context(request: Request) -> dict[str, str | None]:
    """IP and user agent for the audit trail (spec section 30)."""
    forwarded = request.headers.get("x-forwarded-for")
    ip = forwarded.split(",")[0].strip() if forwarded else (
        request.client.host if request.client else None
    )
    return {"ip_address": ip, "user_agent": request.headers.get("user-agent")}
