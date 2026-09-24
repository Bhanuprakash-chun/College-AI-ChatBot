"""Password hashing and JWT issuing/verification.

Uses bcrypt directly (rather than passlib, which is unmaintained against
bcrypt 4.x/5.x) and PyJWT for signed access tokens with an expiry claim.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from app.core.config import settings

# bcrypt truncates silently past 72 bytes; we reject longer inputs instead.
BCRYPT_MAX_BYTES = 72


class TokenError(Exception):
    """Raised when a JWT is missing, malformed, expired, or has a bad signature."""


def hash_password(plain_password: str) -> str:
    password_bytes = plain_password.encode("utf-8")
    if len(password_bytes) > BCRYPT_MAX_BYTES:
        raise ValueError("Password must be at most 72 bytes.")
    salt = bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS)
    return bcrypt.hashpw(password_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        password_bytes = plain_password.encode("utf-8")
        if len(password_bytes) > BCRYPT_MAX_BYTES:
            return False
        return bcrypt.checkpw(password_bytes, hashed_password.encode("utf-8"))
    except (ValueError, TypeError):
        # Malformed stored hash: treat as a failed login, never a 500.
        return False


_DUMMY_HASH: str | None = None


def burn_password_check(plain_password: str) -> None:
    """Spend the same bcrypt time as a real check when the email is unknown,
    so response timing does not reveal which accounts exist."""
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_password("timing-equaliser-not-a-real-password")
    verify_password(plain_password, _DUMMY_HASH)


def create_access_token(
    subject: str | int,
    role: str,
    expires_minutes: int | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> tuple[str, int]:
    """Return (token, expires_in_seconds)."""
    minutes = expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=minutes)

    payload: dict[str, Any] = {
        "sub": str(subject),
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "type": "access",
    }
    if extra_claims:
        payload.update(extra_claims)

    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token, minutes * 60


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT. Raises TokenError on any problem."""
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("Token is invalid.") from exc

    if payload.get("type") != "access":
        raise TokenError("Token is not an access token.")
    return payload
