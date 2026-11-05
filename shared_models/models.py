from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
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


# How the AOI is turned into parts, and so how its results are reported (#219).
# The values match AOIRequest in ast_engine/core/aoi/models.py.
DissolveMode = Literal["full_union", "by_fields", "preserve_features"]
PartPolicy = Literal["multi_part", "exploded"]


class AOIOptions(BaseModel):
    """How the job's AOI is turned into parts. Each part gets its own results.

    dissolve_mode:
        full_union         all rows merged into one area (one result per dataset)
        by_fields          one part per value of dissolve_fields
        preserve_features  one part per row of the AOI
    dissolve_fields: the field(s) to group by. Only with by_fields.
    allow_overlaps: when False, a job whose parts overlap fails.
    part_policy:
        multi_part  a row made of several polygons stays one part
        exploded    one part per polygon. Not available yet (#237).

    A job that leaves the options out gets the defaults: one area, as before.
    """

    model_config = ConfigDict(extra="forbid")

    dissolve_mode: DissolveMode = "full_union"
    dissolve_fields: list[str] = Field(default_factory=list)
    allow_overlaps: bool = False
    part_policy: PartPolicy = "multi_part"

    @field_validator("dissolve_fields")
    @classmethod
    def _clean_dissolve_fields(cls, fields: list[str]) -> list[str]:
        # Same rules as AOIRequest: blank names are dropped, a name given twice is refused.
        cleaned = [name.strip() for name in fields if name.strip()]
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("dissolve_fields cannot name the same field twice")
        return cleaned

    @model_validator(mode="after")
    def _check_combination(self) -> "AOIOptions":
        if self.dissolve_mode == "by_fields" and not self.dissolve_fields:
            raise ValueError("dissolve_mode 'by_fields' needs at least one dissolve field")
        if self.dissolve_mode != "by_fields" and self.dissolve_fields:
            raise ValueError("dissolve_fields can only be used with dissolve_mode 'by_fields'")
        if self.part_policy == "exploded":
            # Waiting on the AOI part builder (#237).
            raise ValueError("part_policy 'exploded' (one part per polygon) is not available yet")
        return self


class JobBase(BaseModel):
    user: str
    date: str

class CreateJob(JobBase):
    region: Regions | str
    area_of_interest: str
    crown_file_number: str
    disposition_number: str
    parcel_number: str
    output_directory: str
    retain_existing_outputs: bool = False
    suppress_tab_3: bool = False
    suppress_map_creation: bool = False
    open_output_directory_on_completion: bool = False
    enable_portable_spreadsheet: bool = False
    registries: list[str] = []
    aoi_id: str
    aoi_name: str
    aoi: dict[str, Any]
    aoi_options: AOIOptions = Field(default_factory=AOIOptions)
    status: JobStatus = JobStatus.QUEUED

    @model_validator(mode="after")
    def _check_dissolve_fields_in_aoi(self) -> "CreateJob":
        # Refuse a dissolve field the AOI's features don't have, before the job is queued.
        features = self.aoi.get("features") or []
        present = {name for feature in features for name in (feature.get("properties") or {})}
        missing = [name for name in self.aoi_options.dissolve_fields if name not in present]
        if features and missing:
            raise ValueError(f"dissolve field(s) not found in the AOI: {', '.join(missing)}")
        return self


class JobQueueItem(BaseModel):
    job_id: str
    user: str
    date: str
    region: str
    aoi_id: str
    aoi_name: str
    output_directory: str
    aoi_options: AOIOptions = Field(default_factory=AOIOptions)
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