# ast/ast_engine/storage/models.py

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

# TODO: Decide if this literal should be centralized
EnvironmentName = Literal["dev", "test", "prod"]


@dataclass(frozen=True)
class StorageConfig:
    bucket: str
    environment: EnvironmentName
    prefix: str = "ast-results"

    # S3-compatible options
    endpoint_url: Optional[str] = None
    region_name: Optional[str] = "ca-central-1"

    # Useful for local/dev testing
    local_root: Optional[Path] = None


@dataclass(frozen=True)
class JobStorageContext:
    job_id: str
    created_date: str  # YYYY-MM-DD