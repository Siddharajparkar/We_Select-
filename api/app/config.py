"""Application configuration (environment variables), validated at startup.

Mirrors the variable names in docs/OFFICE_CONNECTION_AND_TESTING_GUIDE.md and
``.env.azure.example``. Production refuses fakes and the in-memory repository
backend (Prompt B, B3 row 4).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigError(Exception):
    """Raised when the configuration is missing or invalid."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore", case_sensitive=True)

    APP_ENV: Literal["development", "test", "production"] = "development"
    PORT: int = Field(default=8080, ge=1, le=65535)

    # Data layer
    REPO_BACKEND: Literal["memory", "sql"] = "memory"
    DB_SCHEMA: str = "assess"
    DATABASE_URL: str = ""

    # Secrets
    SESSION_SECRET: str = "dev-only-session-secret-change-me-0000"
    PLATFORM_KEY: str = "dev-only-platform-key-change-me-00000"

    # Auth
    COOKIE_SECURE: bool = True
    ARGON2_MEMORY_KIB: int = Field(default=19456, ge=8)  # 19 MiB floor (Prompt A 4.1)
    ARGON2_TIME_COST: int = Field(default=2, ge=1)
    ARGON2_PARALLELISM: int = Field(default=1, ge=1)

    # AI provider
    AI_MODE: Literal["fake", "azure"] = "fake"
    FOUNDRY_API_STYLE: Literal["v1", "azure-deployments"] = "v1"
    FOUNDRY_ENDPOINT: str = ""
    FOUNDRY_KEY: str = ""
    FOUNDRY_DEPLOYMENT: str = "gpt-4o"
    FOUNDRY_API_VERSION: str = ""  # optional; only used by the azure-deployments style
    AI_MAX_OUTPUT_TOKENS: int = Field(default=2000, ge=1)
    AI_DAILY_TOKEN_CAP: int = Field(default=200_000, ge=1)  # per tenant per UTC day
    AI_TIMEOUT_SECONDS: float = Field(default=30.0, gt=0)
    DAILY_GENERATION_LIMIT: int = Field(default=20, ge=1)  # generate jobs per tenant per UTC day

    # Email provider
    EMAIL_MODE: Literal["fake", "azure"] = "fake"
    ACS_CONNECTION_STRING: str = ""
    ACS_SENDER: str = ""

    # Files provider
    FILES_MODE: Literal["memory", "azurite", "azure"] = "memory"
    BLOB_CONNECTION_STRING: str = ""
    BLOB_CONTAINER: str = "jd-files"

    # Telemetry
    APPLICATIONINSIGHTS_CONNECTION_STRING: str = ""
    APPINSIGHTS_SAMPLING_PERCENT: float = Field(default=100.0, gt=0, le=100)

    # URLs
    APP_BASE_URL: str = "http://localhost:8080"
    API_INTERNAL_URL: str = "http://localhost:8080"

    JOB_LOOP_ENABLED: bool = True
    JOB_MAX_CONCURRENT: int = Field(default=3, ge=1, le=10)
    JOB_TICK_SECONDS: float = Field(default=2.0, gt=0)
    JOB_STUCK_SECONDS: int = Field(default=300, ge=10)
    JOB_RETRY_BASE_SECONDS: float = Field(default=5.0, ge=0)
    JOB_SHUTDOWN_GRACE_SECONDS: float = Field(default=20.0, ge=0)
    GIT_SHA: str = "local"
    RETENTION_DAYS: int | None = Field(default=None, ge=1)

    @field_validator("DB_SCHEMA")
    @classmethod
    def _schema_is_identifier(cls, value: str) -> str:
        # The schema name is interpolated into DDL, so it must be a plain identifier.
        if not value or not value.replace("_", "").isalnum():
            raise ValueError("DB_SCHEMA must be a simple identifier (letters, digits, underscore)")
        return value

    @model_validator(mode="after")
    def _cross_field_rules(self) -> Settings:
        problems: list[str] = []
        if self.REPO_BACKEND == "sql" and not self.DATABASE_URL:
            problems.append("DATABASE_URL is required when REPO_BACKEND=sql")
        if self.AI_MODE == "azure" and not (self.FOUNDRY_ENDPOINT and self.FOUNDRY_KEY):
            problems.append("FOUNDRY_ENDPOINT and FOUNDRY_KEY are required when AI_MODE=azure")
        if self.EMAIL_MODE == "azure" and not (self.ACS_CONNECTION_STRING and self.ACS_SENDER):
            problems.append("ACS_CONNECTION_STRING and ACS_SENDER are required when EMAIL_MODE=azure")
        if self.FILES_MODE in ("azurite", "azure") and not self.BLOB_CONNECTION_STRING:
            problems.append("BLOB_CONNECTION_STRING is required when FILES_MODE is azurite or azure")
        if self.is_production:
            if self.AI_MODE != "azure":
                problems.append("AI_MODE must be 'azure' in production")
            if self.EMAIL_MODE != "azure":
                problems.append("EMAIL_MODE must be 'azure' in production")
            if self.FILES_MODE != "azure":
                problems.append("FILES_MODE must be 'azure' in production")
            if self.REPO_BACKEND != "sql":
                problems.append("REPO_BACKEND must be 'sql' in production")
            if len(self.SESSION_SECRET) < 32:
                problems.append("SESSION_SECRET must be at least 32 characters in production")
            if len(self.PLATFORM_KEY) < 32:
                problems.append("PLATFORM_KEY must be at least 32 characters in production")
            if not self.COOKIE_SECURE:
                problems.append("COOKIE_SECURE must be true in production")
            if self.SESSION_SECRET.startswith("dev-only") or self.PLATFORM_KEY.startswith("dev-only"):
                problems.append("development placeholder secrets must not be used in production")
        if problems:
            raise ValueError("; ".join(problems))
        return self

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"


def load_settings(**overrides: object) -> Settings:
    """Build settings from the environment (plus overrides); raise ConfigError on problems."""
    try:
        return Settings(**overrides)  # type: ignore[arg-type]
    except ValueError as exc:  # pydantic.ValidationError is a ValueError
        raise ConfigError(_summarise(exc)) from None


def _summarise(exc: ValueError) -> str:
    errors = getattr(exc, "errors", None)
    if callable(errors):
        parts = []
        for item in errors():
            loc = ".".join(str(p) for p in item.get("loc", ()))
            msg = str(item.get("msg", "invalid")).removeprefix("Value error, ")
            parts.append(f"{loc}: {msg}" if loc else msg)
        return "; ".join(parts)
    return str(exc)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()
