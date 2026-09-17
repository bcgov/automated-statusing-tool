# shared_models/jobs.py

from pydantic import BaseModel
from uuid import UUID
from typing import Iterable, Optional, Any
from status import JobStatus
#Payload structure TODO: ensure aoi crs is same as api and frontend

class AstJob(BaseModel):
    job_id: UUID
    registries: Iterable[tuple[str, Any]]
    created_at: Optional[str] = None
    user: str
    aoi_id: str
    aoi_name: str
    aoi: dict[str, Any] #gdf.to_json()
    status: Optional [JobStatus]