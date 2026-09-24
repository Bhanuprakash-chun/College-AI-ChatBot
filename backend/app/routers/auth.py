"""Authentication routes: register, login, me, logout."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select

from app.core.deps import CurrentUser, DbSession, client_ip
from app.core.rate_limit import login_rate_limit, register_rate_limit
from app.core.security import (
    burn_password_check,
    create_access_token,
    hash_password,
    verify_password,
)
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    TokenResponse,
    UserOut,
)
from app.services.audit_service import (
    ACTION_LOGIN,
    ACTION_LOGIN_FAILED,
    ACTION_LOGOUT,
    ACTION_REGISTER,
    log_action,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])

INVALID_CREDENTIALS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Incorrect email or password.",
    headers={"WWW-Authenticate": "Bearer"},
)


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(register_rate_limit)],
    summary="Register a new student account",
)
def register(payload: RegisterRequest, request: Request, db: DbSession) -> TokenResponse:
    """Self-registration always creates a `student`. Admin rights are granted
    only by an existing admin through `PATCH /admin/users/{id}`.
    """
    email = payload.email.lower().strip()
    existing = db.execute(select(User).where(func.lower(User.email) == email)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    user = User(
        email=email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role=UserRole.STUDENT,
        department=payload.department,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    log_action(
        db,
        ACTION_REGISTER,
        actor=user,
        target_type="user",
        target_id=user.id,
        ip_address=client_ip(request),
    )

    token, expires_in = create_access_token(user.id, user.role.value)
    return TokenResponse(
        access_token=token, expires_in=expires_in, user=UserOut.model_validate(user)
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    dependencies=[Depends(login_rate_limit)],
    summary="Log in and receive a JWT access token",
)
def login(payload: LoginRequest, request: Request, db: DbSession) -> TokenResponse:
    email = payload.email.lower().strip()
    user = db.execute(select(User).where(func.lower(User.email) == email)).scalar_one_or_none()

    # Same generic error for unknown email and wrong password, so the endpoint
    # cannot be used to enumerate registered accounts.
    if user is None:
        burn_password_check(payload.password)
    if user is None or not verify_password(payload.password, user.hashed_password):
        log_action(
            db,
            ACTION_LOGIN_FAILED,
            target_type="user",
            target_id=user.id if user else None,
            detail=f"Failed login for {email}",
            ip_address=client_ip(request),
        )
        raise INVALID_CREDENTIALS

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deactivated. Contact the college administrator.",
        )

    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)

    log_action(
        db,
        ACTION_LOGIN,
        actor=user,
        target_type="user",
        target_id=user.id,
        ip_address=client_ip(request),
    )

    token, expires_in = create_access_token(user.id, user.role.value)
    return TokenResponse(
        access_token=token, expires_in=expires_in, user=UserOut.model_validate(user)
    )


@router.get("/me", response_model=UserOut, summary="Current authenticated user")
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.post("/logout", response_model=MessageResponse, summary="Log out")
def logout(user: CurrentUser, request: Request, db: DbSession) -> MessageResponse:
    """Records the logout for auditing. JWTs are stateless, so the client
    discards the token; tokens remain valid until their `exp` claim.
    """
    log_action(
        db,
        ACTION_LOGOUT,
        actor=user,
        target_type="user",
        target_id=user.id,
        ip_address=client_ip(request),
    )
    return MessageResponse(message="Logged out. Please discard your access token.")
