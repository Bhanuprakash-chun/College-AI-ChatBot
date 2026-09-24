"""Shared FastAPI dependencies: current user resolution and role guards."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import TokenError, decode_access_token
from app.database.session import get_db
from app.models.enums import UserRole
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False, description="JWT access token")

CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials.",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    if credentials is None or not credentials.credentials:
        raise CREDENTIALS_EXCEPTION

    try:
        payload = decode_access_token(credentials.credentials)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CREDENTIALS_EXCEPTION from exc

    user = db.get(User, user_id)
    if user is None:
        raise CREDENTIALS_EXCEPTION
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="This account has been deactivated."
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


class RequireRole:
    """Role guard usable as a dependency: `Depends(RequireRole(UserRole.ADMIN))`.

    Written as a set membership test so additional roles (e.g. FACULTY) can be
    granted access to a route without changing the guard itself.
    """

    def __init__(self, *roles: UserRole):
        self.roles = set(roles)

    def __call__(self, user: CurrentUser) -> User:
        if user.role not in self.roles:
            allowed = ", ".join(sorted(r.value for r in self.roles))
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action requires one of these roles: {allowed}.",
            )
        return user


require_admin = RequireRole(UserRole.ADMIN)
AdminUser = Annotated[User, Depends(require_admin)]
DbSession = Annotated[Session, Depends(get_db)]


def client_ip(request: Request) -> str:
    """Address recorded in audit logs. See rate_limit.client_identifier."""
    from app.core.rate_limit import client_identifier

    return client_identifier(request)
