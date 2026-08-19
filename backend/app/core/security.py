"""Password hashing and JWT issuance."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# bcrypt truncates silently past 72 bytes, so the length is capped explicitly
# on the way in rather than letting a long password become a shorter one.
_MAX_PASSWORD_BYTES = 72

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(_truncate(password))


#: Unambiguous alphabet: no O/0, no l/1/I. A generated password gets read off
#: a screen and typed by hand, and one nobody can transcribe is a support call.
_PASSWORD_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"


def generate_password(length: int = 12) -> str:
    """A random initial password, for a new account or an admin reset."""
    return "".join(secrets.choice(_PASSWORD_ALPHABET) for _ in range(length))


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(_truncate(plain), hashed)
    except ValueError:
        # Malformed hash in the row -- treat as a failed login, not a 500.
        return False


def _truncate(password: str) -> str:
    encoded = password.encode("utf-8")
    if len(encoded) <= _MAX_PASSWORD_BYTES:
        return password
    return encoded[:_MAX_PASSWORD_BYTES].decode("utf-8", errors="ignore")


def create_access_token(
    subject: str | uuid.UUID,
    extra_claims: dict[str, Any] | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    """Issue a signed access token.

    Role and permission claims are embedded so that read-only authorisation
    checks do not need a database round trip, but anything that mutates data
    re-reads the user, so a revoked role takes effect on the next write even
    if an old token is still in flight.
    """
    now = datetime.now(UTC)
    expire = now + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload: dict[str, Any] = {
        "sub": str(subject),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "type": "access",
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any] | None:
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
    except JWTError:
        return None
    if payload.get("type") != "access":
        return None
    return payload
