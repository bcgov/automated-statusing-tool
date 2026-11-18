from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal


class Settings(BaseSettings):
    # App environment
    environment: Literal["development", "staging", "production"] = "development"

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_file: str | None = None

    # System validation flags
    validate_oracle_connection: bool = True
    validate_required_paths: list[str] = Field(default_factory=list)  # Paths to check exist

    # Database Connection Settings
    oracle_host: str | None = None
    oracle_database: str | None = None
    oracle_port: int | None = 1521
    oracle_user: str | None = None
    oracle_password: SecretStr | None = None

    # S3 Connections
    s3_max_retries: int = 5
    s3_retry_mode: Literal["standard"] = "standard"
    s3_use_ssl: bool = True

    # retain spatial results
    record_spatial: bool = False

    # temporary directory for storing results
    temp_dir: str | None = None

    # storage of results
    deployment: Literal["DEV", "TEST", "PROD"] = "DEV"
    storage_type: Literal["S3", "local"] = "local"
    results_local_root: str = "ast/local"
    results_s3_endpoint_url: str | None = None
    results_s3_access_id: str | None = None
    results_s3_key: SecretStr | None = None
    results_s3_bucket: str | None = None
    results_prefix: str = "ast-results"

    # redis
    job_queue: str = "ast_job_queue"
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_database: int = 0
    redis_password: SecretStr | None = None
    # how long a job's status record is kept in Redis after its last update.
    # The record holds the submitter's name and email, so it is not kept forever.
    job_status_ttl_seconds: int = 7 * 24 * 60 * 60

    # engine settings
    system_crs: str = "EPSG:3005"

    # largest uploaded area-of-interest file the API accepts, in bytes
    max_upload_bytes: int = 20 * 1024 * 1024

    # Login check. Every route asks for an access token from the login service
    # the frontend signs people in with (see ast_api/auth.py).
    #   oidc_issuer: the login service's address, as in a token's "iss", e.g.
    #       "https://loginproxy.gov.bc.ca/auth/realms/standard"
    #   oidc_audience: this application's client id, as in a token's "aud"
    #   oidc_jwks_url: where the signing keys are published; worked out from
    #       the issuer when not set
    # auth_required is on unless switched off, and with it on and no issuer or
    # audience set the API refuses every request rather than serve unchecked.
    # Switch it off only to work locally without a login service.
    auth_required: bool = True
    oidc_issuer: str | None = None
    oidc_audience: str | None = None
    oidc_jwks_url: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        # The .env file is shared with docker compose, which keeps values of
        # its own there (NO_PROXY, BACKEND_PORT...). Those are not settings.
        extra="ignore",
    )

    def validate_system(self) -> list[str]:
        """Validate environment before orchestration. Returns list of issues."""
        issues: list[str] = []

        for required_path in self.validate_required_paths:
            if not required_path:
                continue
            if not Path(required_path).expanduser().exists():
                issues.append(f"Required path does not exist: {required_path}")

        if self.validate_oracle_connection:
            for field_name in ("oracle_host", "oracle_database", "oracle_user"):
                if hasattr(self, field_name):
                    value = getattr(self, field_name)
                    if value in (None, ""):
                        issues.append(f"Oracle configuration missing: {field_name}")
            if hasattr(self, "oracle_password") and self.oracle_password is None:
                issues.append("Oracle configuration missing: oracle_password")

        return issues
