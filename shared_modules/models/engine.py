from pydantic import BaseModel, Field
from typing import Any, Optional, Iterable
from enum import StrEnum
from uuid import UUID, uuid4
from models import JobStatus, AOIOptions

class AstEngineJob(BaseModel):
    job_id: int
    registries: Iterable[tuple[str, Any]]
    created_at: Optional[str] = None
    user: str
    aoi_id: str
    aoi_name: str
    aoi: dict[str, Any] #gdf.to_json()
    aoi_options: AOIOptions = Field(default_factory=AOIOptions)
    status: Optional [JobStatus]