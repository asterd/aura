from __future__ import annotations

from functools import cached_property

from pydantic import AnyHttpUrl, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(alias="DATABASE_URL")
    alembic_database_url: str | None = Field(default=None, alias="ALEMBIC_DATABASE_URL")
    redis_url: str = Field(alias="REDIS_URL")
    qdrant_url: AnyHttpUrl = Field(alias="QDRANT_URL")
    s3_endpoint_url: AnyHttpUrl = Field(alias="S3_ENDPOINT_URL")
    s3_access_key_id: str = Field(alias="S3_ACCESS_KEY_ID")
    s3_secret_access_key: SecretStr = Field(alias="S3_SECRET_ACCESS_KEY")
    s3_bucket_name: str = Field(alias="S3_BUCKET_NAME")
    s3_region: str = Field(alias="S3_REGION")
    s3_secure: bool = Field(default=False, alias="S3_SECURE")
    litellm_base_url: AnyHttpUrl = Field(alias="LITELLM_BASE_URL")
    okta_jwks_url: AnyHttpUrl = Field(alias="OKTA_JWKS_URL")
    okta_issuer_override: AnyHttpUrl | None = Field(default=None, alias="OKTA_ISSUER")
    okta_audience: str = Field(default="api://default", alias="OKTA_AUDIENCE")
    langfuse_base_url: AnyHttpUrl = Field(alias="LANGFUSE_BASE_URL")
    langfuse_secret_key: SecretStr = Field(alias="LANGFUSE_SECRET_KEY")
    postgres_connect_timeout_s: float = 5.0
    service_check_timeout_s: float = 5.0
    api_prefix: str = "/api/v1"

    @cached_property
    def migration_database_url(self) -> str:
        if self.alembic_database_url:
            return self.alembic_database_url
        return self.database_url.replace("://aura_app:", "://aura_service:", 1)

    @cached_property
    def sync_database_url(self) -> str:
        return self.database_url.replace("+asyncpg", "", 1)

    @cached_property
    def okta_issuer(self) -> str:
        if self.okta_issuer_override:
            return str(self.okta_issuer_override)
        jwks_url = str(self.okta_jwks_url).rstrip("/")
        if jwks_url.endswith("/v1/keys"):
            return jwks_url[: -len("/v1/keys")]
        return jwks_url


settings = Settings()
