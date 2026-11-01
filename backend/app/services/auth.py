from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.models.user import User

password_hash = PasswordHash.recommended()


class DuplicateUserError(Exception):
    pass


def normalize_email(email: str) -> str:
    return email.strip().casefold()


def register_user(db: Session, *, email: str, password: str, display_name: str) -> User:
    normalized = normalize_email(email)
    existing = db.scalar(select(User).where(User.email == normalized))
    if existing:
        raise DuplicateUserError
    user = User(
        email=normalized,
        password_hash=password_hash.hash(password),
        display_name=display_name.strip(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, *, email: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.email == normalize_email(email)))
    if user is None or not password_hash.verify(password, user.password_hash):
        return None
    return user


def issue_access_token(user: User) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user.id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm="HS256")


def read_access_token(token: str) -> int:
    settings = get_settings()
    payload = jwt.decode(token, settings.jwt_secret.get_secret_value(), algorithms=["HS256"])
    return int(payload["sub"])
