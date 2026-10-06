from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr
from typing import Literal

class Settings(BaseSettings):
    # App environment
    environment: Literal["development", "staging", "production"] = "development"

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_file: str | None = None
    
    # System validation flags
    validate_oracle_connection: bool = True
    validate_required_paths: list[str] = []  # Paths to check exist

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
    deployment: Literal["DEV","TEST","PROD"] = "DEV"
    storage_type: Literal["S3","local"] = "local"
    results_local_root: str = 'ast/local'
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
        issues: list = []
        if self.validate_required_paths:
            # Check paths exist
            pass
        return issues