import pytest
from pydantic import ValidationError

from backend.app.core.config import OpenAlexConfigurationError, Settings


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


def test_openalex_credentials_load_from_environment(monkeypatch):
    dummy_key = "dummy-openalex-key-for-tests"
    dummy_contact = "researcher@example.test"
    monkeypatch.setenv("OPENALEX_API_KEY", dummy_key)
    monkeypatch.setenv("OPENALEX_MAILTO", dummy_contact)

    settings = Settings(_env_file=None)

    assert settings.openalex_api_key.get_secret_value() == dummy_key
    assert settings.openalex_mailto == dummy_contact
    settings.require_openalex_credentials()


@pytest.mark.parametrize(
    ("api_key", "contact", "expected_field"),
    [
        ("", "researcher@example.test", "OPENALEX_API_KEY"),
        ("dummy-openalex-key-for-tests", "", "OPENALEX_MAILTO"),
        ("dummy-openalex-key-for-tests", "not-an-email", "OPENALEX_MAILTO"),
    ],
)
def test_openalex_missing_or_invalid_credentials_raise_safe_error(
    api_key, contact, expected_field
):
    settings = Settings(
        _env_file=None,
        openalex_api_key=api_key,
        openalex_mailto=contact,
    )

    with pytest.raises(OpenAlexConfigurationError, match=expected_field) as error:
        settings.require_openalex_credentials()

    if api_key:
        assert api_key not in str(error.value)


def test_openalex_api_key_is_masked_in_settings_output():
    dummy_key = "dummy-openalex-key-for-tests"
    settings = Settings(
        _env_file=None,
        openalex_api_key=dummy_key,
        openalex_mailto="researcher@example.test",
    )

    assert dummy_key not in str(settings.openalex_api_key)
    assert dummy_key not in repr(settings.openalex_api_key)
    assert dummy_key not in repr(settings)


def test_fastembed_cache_path_environment_is_normalized(monkeypatch):
    monkeypatch.setenv("FASTEMBED_CACHE_PATH", " /tmp/scholarsignal-models ")
    settings = Settings(_env_file=None)
    assert settings.fastembed_cache_path == "/tmp/scholarsignal-models"

    monkeypatch.setenv("FASTEMBED_CACHE_PATH", "")
    assert Settings(_env_file=None).fastembed_cache_path is None
