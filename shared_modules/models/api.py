from pydantic import BaseModel, Field
from typing import Any
from enum import StrEnum
from uuid import UUID, uuid4
from datetime import datetime, UTC
from shared_modules.models.models import JobStatus
from pathlib import Path

class JobStatusResponse(BaseModel):
    job_id: UUID
    status: JobStatus

class JobRequest(BaseModel):
    job_id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    aoi: dict[str, Any]

class DataStatus(StrEnum):
    ACTIVE="Active"
    RETIRED="Retired"

class Registry(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    path: Path

class RegistrySummary(BaseModel):
    id: str
    name: str
    
    model_config = {"from_attributes": True}