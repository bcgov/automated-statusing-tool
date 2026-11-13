from pydantic import BaseModel, ConfigDict, Field
from enum import Enum 
from typing import Literal, Any, Dict, Optional
from dataclasses import dataclass, field
import yaml


class Regions(str, Enum): 
    Cariboo = "Cariboo"
    KootenayBoundary = "Kootenay Boundary"
    ThompsonOkanagan = "Thompson Okanagan"
    Omineca = "Omineca"
    Northeast = "Northeast"
    Skeena = "Skeena"
    SouthCoast = "South Coast"
    WestCoast = "West Coast"

class JobStatus(str, Enum):
    QUEUED = "Queued"
    PROCESSING = "Processing"
    PUBLISHING = "Publishing"
    COMPLETED = "Completed"
    FAILED = "Failed"


class CreateJob(BaseModel):
    name: str
    email: str
    region: Regions | str
    source: Literal["1", "2"]
    crown_file_number: str | None = None
    disposition_number: str | None = None
    parcel_number: str | None = None
    generate_maps: bool = False
    export_overlap_results: bool = False
    status: JobStatus = JobStatus.QUEUED


class JobQueueItem(BaseModel):
    job_id: str
    name: str
    email: str
    region: str
    source: Literal["1", "2"]
    status: JobStatus = JobStatus.QUEUED

class JobPayload(BaseModel):
    job: CreateJob
    item: JobQueueItem

@dataclass
class ArtifactRecord:
    key: str
    content_type: str
    sha256: Optional[str] = None
    uri: Optional[str] = None

@dataclass
class JobManifest:
    schema_version: int
    job_id: str
    created_at: str
    completed_at: Optional[str]
    status: str
    engine_name: str
    engine_version: str
    artifacts: Dict[str, ArtifactRecord] = field(default_factory=dict)
    spatial: Optional[Dict[str, Any]] = None
    inputs: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "job_id": self.job_id,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "status": self.status,
            "engine": {
                "name": self.engine_name,
                "version": self.engine_version,
            },
            "inputs": self.inputs or {},
            "artifacts": {
                name: {
                    key: value
                    for key, value in {
                        "key": artifact.key,
                        "content_type": artifact.content_type,
                        "sha256": artifact.sha256,
                        "uri": artifact.uri,
                    }.items()
                    if value is not None
                }
                for name, artifact in self.artifacts.items()
            },
            "spatial": self.spatial or {},
        }

    def to_yaml(self) -> str:
        return yaml.safe_dump(
            self.to_dict(),
            sort_keys=False,
            allow_unicode=True,
        )