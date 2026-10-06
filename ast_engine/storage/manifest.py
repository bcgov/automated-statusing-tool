# ast/ast_engine/storage/manifest.py

from pydantic import BaseModel, Field
from typing import Any, Dict, Optional
from uuid import UUID

import yaml


class ArtifactRecord(BaseModel):
    key: str
    content_type: str
    sha256: Optional[str] = None
    uri: Optional[str] = None
    metadata: Optional[Dict[str,Any]] = None


class JobManifest(BaseModel):
    schema_version: int
    job_id: UUID
    user: str
    created_at: str
    completed_at: Optional[str]
    execution_time: float
    status: str
    engine_name: str
    engine_version: str
    artifacts: Dict[str, ArtifactRecord] = Field(default_factory=dict)
    spatial: Optional[Dict[str, Any]] = None
    inputs: Optional[Dict[str, Any]] = None

    # def to_dict(self) -> Dict[str, Any]:
    #     return {
    #         "schema_version": self.schema_version,
    #         "job_id": self.job_id,
    #         "user": self.user,
    #         "created_at": self.created_at,
    #         "completed_at": self.completed_at,
    #         "execution_time": self.execution_time,
    #         "status": self.status,
    #         "engine": {
    #             "name": self.engine_name,
    #             "version": self.engine_version,
    #         },
    #         "inputs": self.inputs or {},
    #         "artifacts": {
    #             name: {
    #                 key: value
    #                 for key, value in {
    #                     "key": artifact.key,
    #                     "content_type": artifact.content_type,
    #                     "sha256": artifact.sha256,
    #                     "uri": artifact.uri,
    #                     "metadata": artifact.metadata,
    #                 }.items()
    #                 if value is not None
    #             }
    #             for name, artifact in self.artifacts.items()
    #         },
    #         "spatial": self.spatial or {},
    #     }
    # def to_yaml(self) -> str:
    #     return yaml.safe_dump(
    #         self.to_dict(),
    #         sort_keys=False,
    #         allow_unicode=True,
    #     )