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


# Values of the job "source" field: where the area of interest comes from.
SOURCE_TANTALIS = "1"
SOURCE_UPLOAD = "2"


class JobQueueItem(BaseModel):
    """One statusing job, as it travels between the API and the engine worker.

    This is the contract both sides share. The API builds one for every
    submitted job and pushes it onto the Redis job queue; the worker pops it,
    runs the analysis and reports back by updating the same record in the job
    status store (see shared_models/job_store.py).

    The area of interest arrives one of two ways, chosen by `source`:
      - TANTALIS ("1"): the three identifiers are sent and the worker looks the
        parcel up in BCGW, because the worker is the side that holds the
        database connection;
      - Upload ("2"): the API has already read the uploaded file, so `aoi`
        carries the shape itself.

    aoi          a GeoJSON FeatureCollection in EPSG:4326 (longitude/latitude),
                 geometry only. It is on the queue message but is left out of
                 the status record - nothing reads it back and it can be large.
    created_at   when the API accepted the job, as an ISO 8601 UTC timestamp.
    completed_at when the worker finished it, whether it completed or failed.
    error        why the job failed, in words a user can act on; empty otherwise.

    The fields added for the worker all have defaults, so a record written
    before they existed still loads.
    """

    job_id: str
    name: str
    email: str
    region: str
    source: Literal["1", "2"]
    status: JobStatus = JobStatus.QUEUED
    crown_file_number: str | None = None
    disposition_number: str | None = None
    parcel_number: str | None = None
    aoi: Dict[str, Any] | None = None
    generate_maps: bool = False
    export_overlap_results: bool = False
    created_at: str | None = None
    completed_at: str | None = None
    error: str | None = None

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