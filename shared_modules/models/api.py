from pydantic import BaseModel, Field
from typing import Any
from enum import StrEnum
from uuid import UUID, uuid4
from shared_models.models import JobStatus


class JobStatusResponse(BaseModel):
    job_id: UUID
    status: JobStatus

class JobRequest(BaseModel):
    job_id: UUID = Field(default_factory=uuid4)
    aoi: dict[str, Any]

