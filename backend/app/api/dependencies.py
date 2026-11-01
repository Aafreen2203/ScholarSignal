import jwt
from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.models.user import User
from backend.app.services.auth import read_access_token


def current_user(
    access_token: str | None = Cookie(default=None), db: Session = Depends(get_db)
) -> User:
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )
    try:
        user_id = read_access_token(access_token)
    except (jwt.InvalidTokenError, ValueError, KeyError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session"
        ) from None
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session"
        )
    return user


def optional_current_user(
    access_token: str | None = Cookie(default=None), db: Session = Depends(get_db)
) -> User | None:
    """Return the authenticated user when present; public search remains public."""
    if not access_token:
        return None
    try:
        user_id = read_access_token(access_token)
    except (jwt.InvalidTokenError, ValueError, KeyError):
        return None
    return db.get(User, user_id)
