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
    # Folder holding Oracle's client libraries (Instant Client). Only needed
    # for a BCGW account that is refused without them (error DPY-3015).
    oracle_client_lib_dir: str | None = None
    
    # S3 Connections
    s3_max_retries: int = 5
    s3_retry_mode: Literal["standard"] = "standard"
    s3_use_ssl: bool = True

    # Registry storage settings
    # registry_output_path is where the spreadsheet ingestion writes the registry
    # yaml files, and so also where the worker loads a job's registries from.
    registry_spreadsheet_path: str | None = None
    registry_output_path: str | None = None

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
    # how long a job's status record is kept in Redis after its last update.
    # The record holds the submitter's name and email, so it is not kept forever.
    job_status_ttl_seconds: int = 7 * 24 * 60 * 60

    # engine settings
    system_crs: str = "EPSG:3005"

    # The address people reach the API at, e.g. "https://ast.example.gov.bc.ca".
    # When set, the status report links to a job's maps through the API, so the
    # links work from a downloaded copy of the report. When not set the links
    # are relative ("maps/<name>.html") and work in a copy of the job's folder.
    api_public_url: str | None = None

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
        issues: list = []
        if self.validate_required_paths:
            # Check paths exist
            pass
        return issues