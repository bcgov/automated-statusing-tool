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
    validate_required_paths: list[str] = []  # Paths to check exist
    
    #S3 Connections
    s3_max_retries: int = 5
    s3_retry_mode: Literal["standard"] = "standard"


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