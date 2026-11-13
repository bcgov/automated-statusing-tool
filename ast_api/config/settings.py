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

    # engine settings
    system_crs: str = "EPSG:3005"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
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
