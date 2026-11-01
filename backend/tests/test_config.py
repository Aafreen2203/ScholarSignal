import pytest
from pydantic import ValidationError

from backend.app.core.config import Settings


def test_production_settings_reject_default_secret_and_insecure_cookie():
    with pytest.raises(ValidationError, match="explicitly configured"):
        Settings(
            app_env="production",
            jwt_secret="development-only-change-me-before-deploying",
            cookie_secure=True,
        )
    with pytest.raises(ValidationError, match="COOKIE_SECURE"):
        Settings(app_env="production", jwt_secret="an-explicitly-configured-long-secret")


def test_production_settings_accept_explicit_secret_and_secure_cookie():
    settings = Settings(
        app_env="production", jwt_secret="an-explicitly-configured-long-secret", cookie_secure=True
    )
    assert settings.cookie_secure is True
