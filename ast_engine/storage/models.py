# ast/ast_engine/storage/models.py

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional
from botocore.config import Config

# TODO: Decide if this literal should be centralized
EnvironmentName = Literal["dev", "test", "prod"]

# TODO: Should retries max_attempts and mode be configurable? Load from application config!
MAX_RETRIES = 5
RETRY_MODE = "standard" 



@dataclass(frozen=True)
class StorageConfig:
    bucket: str
    environment: EnvironmentName
    prefix: str = "ast-results"

    # S3-compatible options
    access_id: Optional[str] = None
    access_key: Optional[str] = None
    use_ssl: bool = True
    endpoint_url: Optional[str] = None
    config: Optional[Config] = Config(request_checksum_calculation="when_required",
                   response_checksum_validation="when_required",
                   retries={'max_attempts': MAX_RETRIES, 'mode': RETRY_MODE})
    # Useful for local/dev testing
    local_root: Optional[Path] = None


@dataclass(frozen=True)
class JobStorageContext:
    job_id: str
    created_date: str  # YYYY-MM-DD