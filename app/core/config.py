from functools import lru_cache
from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _async_database_url(value: str) -> str:
    if value.startswith("postgresql://"):
        return value.replace("postgresql://", "postgresql+asyncpg://", 1)
    if value.startswith("postgres://"):
        return value.replace("postgres://", "postgresql+asyncpg://", 1)
    if value.startswith("sqlite:///"):
        return value.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = "FutureX Reviewer"
    app_env: str = Field(default="development", alias="APP_ENV")

    database_url: str = Field(
        default="sqlite+aiosqlite:///./futurex_reviewer.db",
        alias="DATABASE_URL",
    )

    jwt_secret: str = Field(default="dev-change-me", alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_expire_minutes: int = Field(default=60 * 24, alias="JWT_EXPIRE_MINUTES")

    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4.1-mini", validation_alias=AliasChoices("OPENAI_MODEL", "MODEL"))

    graphify_command: str = Field(default="graphify", alias="GRAPHIFY_COMMAND")
    projects_dir: str = Field(default="./projects", alias="PROJECTS_DIR")
    redis_url: str | None = Field(default=None, validation_alias=AliasChoices("REDIS_UR", "REDIS_URL"))

    cors_origins: list[str] = Field(default_factory=lambda: ["*"], alias="CORS_ORIGINS")

    internal_auth_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("INTERNAL_AUTH_ENABLED", "PROJECT_REVIEW_INTERNAL_AUTH_ENABLED"),
    )
    internal_auth_issuer: str | None = Field(
        default=None,
        validation_alias=AliasChoices("INTERNAL_AUTH_ISSUER", "PROJECT_REVIEW_INTERNAL_AUTH_ISSUER"),
    )
    internal_auth_audience: str | None = Field(
        default=None,
        validation_alias=AliasChoices("INTERNAL_AUTH_AUDIENCE", "PROJECT_REVIEW_INTERNAL_AUTH_AUDIENCE"),
    )
    internal_auth_algorithm: str = Field(
        default="HS256",
        validation_alias=AliasChoices("INTERNAL_AUTH_ALGORITHM", "PROJECT_REVIEW_INTERNAL_AUTH_ALGORITHM"),
    )
    internal_auth_jwt_secret: str | None = Field(
        default=None,
        validation_alias=AliasChoices("INTERNAL_AUTH_JWT_SECRET", "PROJECT_REVIEW_INTERNAL_AUTH_JWT_SECRET"),
    )
    internal_auth_jwt_public_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("INTERNAL_AUTH_JWT_PUBLIC_KEY", "PROJECT_REVIEW_INTERNAL_AUTH_JWT_PUBLIC_KEY"),
    )
    internal_auth_required_service: str | None = Field(
        default=None,
        validation_alias=AliasChoices("INTERNAL_AUTH_REQUIRED_SERVICE", "PROJECT_REVIEW_INTERNAL_AUTH_REQUIRED_SERVICE"),
    )

    api_rate_limit_enabled: bool = Field(default=False, alias="API_RATE_LIMIT_ENABLED")
    api_rate_limit_requests: int = Field(default=120, alias="API_RATE_LIMIT_REQUESTS")
    api_rate_limit_window_seconds: int = Field(default=60, alias="API_RATE_LIMIT_WINDOW_SECONDS")
    review_worker_enabled: bool = Field(default=True, alias="REVIEW_WORKER_ENABLED")
    review_worker_poll_seconds: float = Field(default=3.0, alias="REVIEW_WORKER_POLL_SECONDS")
    review_worker_stale_seconds: int = Field(default=1800, alias="REVIEW_WORKER_STALE_SECONDS")

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        return _async_database_url(value)

    @property
    def effective_jwt_secret(self) -> str:
        return self.internal_auth_jwt_secret or self.jwt_secret


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
