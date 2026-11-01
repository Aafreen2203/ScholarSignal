from functools import lru_cache

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class OpenAlexConfigurationError(ValueError):
    """Safe configuration error that never includes credential values."""


class Settings(BaseSettings):
    app_env: str = "development"
    frontend_origin: str = "http://localhost:3000"
    database_url: str = (
        "postgresql+psycopg://scholarsignal:scholarsignal@localhost:5432/scholarsignal"
    )
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: SecretStr = SecretStr("development-only-change-me-before-deploying")
    access_token_minutes: int = 30
    cookie_secure: bool = False
    openalex_api_key: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("OPENALEX_API_KEY", "openalex_api_key"),
    )
    openalex_mailto: str = Field(
        default="",
        validation_alias=AliasChoices("OPENALEX_MAILTO", "openalex_mailto"),
    )
    openalex_base_url: str = "https://api.openalex.org"
    openalex_per_page: int = 100
    openalex_default_limit: int = 25
    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_model_version: str = "fastembed-0.9.1"
    embedding_batch_size: int = 32
    fastembed_cache_path: str | None = None
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("fastembed_cache_path", mode="before")
    @classmethod
    def normalize_cache_path(cls, value):
        return value.strip() or None if isinstance(value, str) else value

    @field_validator("jwt_secret")
    @classmethod
    def validate_secret(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError("JWT_SECRET must contain at least 32 characters")
        return value

    @model_validator(mode="after")
    def validate_production_security(self):
        if self.app_env.casefold() == "production":
            if self.jwt_secret.get_secret_value() == "development-only-change-me-before-deploying":
                raise ValueError("JWT_SECRET must be explicitly configured in production")
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE must be enabled in production")
        return self

    def require_openalex_credentials(self) -> None:
        if not self.openalex_api_key.get_secret_value().strip():
            raise OpenAlexConfigurationError(
                "OPENALEX_API_KEY is required to run OpenAlex ingestion."
            )
        if not self.openalex_mailto.strip() or "@" not in self.openalex_mailto:
            raise OpenAlexConfigurationError(
                "OPENALEX_MAILTO must be a valid contact email to run OpenAlex ingestion."
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
