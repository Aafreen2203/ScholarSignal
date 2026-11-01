from fastapi import APIRouter, Depends, HTTPException, Response, status
from redis import Redis
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.api.dependencies import current_user
from backend.app.core.config import get_settings
from backend.app.core.redis import get_redis_client
from backend.app.db.session import get_db
from backend.app.models.user import User
from backend.app.schemas.auth import LoginRequest, RegisterRequest, UserResponse
from backend.app.services.auth import (
    DuplicateUserError,
    authenticate_user,
    issue_access_token,
    register_user,
)
from backend.app.services.rate_limit import (
    RateLimitExceeded,
    RateLimitUnavailable,
    enforce_auth_rate_limit,
)

router = APIRouter(prefix="/auth", tags=["authentication"])


def set_session_cookie(response: Response, user: User) -> None:
    settings = get_settings()
    response.set_cookie(
        "access_token",
        issue_access_token(user),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
        max_age=settings.access_token_minutes * 60,
    )


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    response: Response,
    db: Session = Depends(get_db),
    redis: Redis = Depends(get_redis_client),
):
    try:
        enforce_auth_rate_limit(redis, action="register", email=str(payload.email))
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=429,
            detail="Too many account creation attempts",
            headers={"Retry-After": str(exc.retry_after)},
        ) from None
    except RateLimitUnavailable:
        raise HTTPException(
            status_code=503, detail="Authentication service is temporarily unavailable"
        ) from None
    try:
        user = register_user(
            db,
            email=str(payload.email),
            password=payload.password,
            display_name=payload.display_name,
        )
    except DuplicateUserError:
        raise HTTPException(
            status_code=409, detail="An account with this email already exists"
        ) from None
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="An account with this email already exists"
        ) from None
    set_session_cookie(response, user)
    return user


@router.post("/login", response_model=UserResponse)
def login(
    payload: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
    redis: Redis = Depends(get_redis_client),
):
    try:
        enforce_auth_rate_limit(redis, action="login", email=str(payload.email))
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=429,
            detail="Too many sign-in attempts",
            headers={"Retry-After": str(exc.retry_after)},
        ) from None
    except RateLimitUnavailable:
        raise HTTPException(
            status_code=503, detail="Authentication service is temporarily unavailable"
        ) from None
    user = authenticate_user(db, email=str(payload.email), password=payload.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Email or password is incorrect")
    set_session_cookie(response, user)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response):
    response.delete_cookie(
        "access_token", path="/", httponly=True, samesite="lax", secure=get_settings().cookie_secure
    )


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(current_user)):
    return user
