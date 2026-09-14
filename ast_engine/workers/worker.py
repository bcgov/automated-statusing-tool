import logging
from pathlib import Path
import geopandas as gpd
from datetime import datetime, UTC
from io import StringIO
from uuid import UUID
from enum import StrEnum
from typing import Optional, Any
from pydantic import BaseModel

from ast_engine.core.aoi.aoi_builder import AOIBuilder, AOIRequest
from ast_engine.core.execution import run_analysis, build_tasks
from ast_engine.core.results import AstResults
from ast_engine.storage.publisher import ResultsPublisher
from ast_engine.storage import create_results_writer, JobStorageContext
from ast_engine.storage.models import OperatorArtifact
from ast_engine.config.settings import Settings

logger = logging.getLogger(__name__)
settings = Settings()

class JobStatus(StrEnum):
    QUEUED = "Queued"
    PROCESSING = "Processing"
    PUBLISHING = "Publishing"
    COMPLETED = "Completed"
    FAILED = "Failed"

#Payload structure TODO: ensure aoi crs is same as api and frontend
class AstJob(BaseModel):
    job_id: UUID
    registries: list[str, Any]
    created_at: Optional[str] = None
    user: str
    aoi_id: str
    aoi_name: str
    aoi: dict[str, Any] #gdf.to_json()
    status: Optional [JobStatus]

    
def publish_results(job: AstJob, ast_results: AstResults):
    # Publishes AstResults to local disk storage or S3

    logging.debug("Publish [job-id: %s]: Started",job.job_id)
    job.status = JobStatus.PUBLISHING

    # hey -- AstResults is a Pydantic model, so we can serialize it to JSON directly
    output_dir = Path(settings.temp_dir) / job.job_id
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_results_file = output_dir / "raw_results.json"
    raw_results_file.write_text(ast_results.model_dump_json())

    # catalog the operator artifacts
    operator_outputs = []
    for dataset_group in ast_results.results:
        for result in dataset_group.results:
            if result.spatial_link:
                operator_output = OperatorArtifact(registry="blablabla",operator=result.operator_type,dataset_name=dataset_group.dataset_name,path=result.spatial_link)
                operator_outputs.append(operator_output)
    
    completed_at = datetime.now(UTC).isoformat()

    # Publisher will upload all items in the manifest paths
    storage_context = JobStorageContext(job_id=job.job_id,created_date=job.created_at)
    writer = create_results_writer(context=storage_context)
    publisher = ResultsPublisher(writer=writer)
    artifacts = publisher.publish_job_results(
        job_id=job.job_id,
        user=job.user,
        created_at=job.created_at,
        completed_at=completed_at,
        execution_time=ast_results.execution_time,
        status="success",
        engine_version="1.0.0", # TODO: draw from config
        raw_results_json=raw_results_file,
        operator_outputs=operator_outputs
        # Include other optional paths as they become available:
        # extracted_gpkg=..., 
        # aoi_geojson=...,
    )
    logging.debug("Publish [job-id: %s]: Completed", job.job_id)
    return {"job":job, "artifacts": artifacts}

def run_worker(job: AstJob, publish: bool = False):
    # executes ast_engine and optionally publishes using storage settings in ast_engine.config.settings
    # returns job with updated status
    logger.info("Worker Processing [job-id:%s]", job.aoi_id)
    if publish is True:
        logger.info("Worker Processing [job-id:%s] -- Publication On: %s storage", job.aoi_id,settings.storage_type)
    else:
        logger.info("Worker Processing [job-id:%s] -- Publication OFF", job.aoi_id)
        
    job.status = JobStatus.PROCESSING
    
    try:
        # Form the AOI
        # TODO: Is from features what we want to use here?Coordinate with API
        gdf = gpd.read_file(StringIO(job.aoi))
        
        request = AOIRequest(aoi_id=job.aoi_id, name=job.aoi_name, target_crs= settings.system_crs)
        aoi = AOIBuilder().from_gdf(request, gdf)

        # TODO: Are registries a list provided by the api. 
        # Perhaps they should be appended to a base config registry
        tasks = build_tasks(job.registries)
        
        # engage engine
        ast_results = run_analysis(
            aoi=aoi,
            tasks=tasks,
            job_id=job.job_id,
        )

        # option pubilsh results
        if publish is True:
            publish_results(ast_results=ast_results)
        job.status = JobStatus.COMPLETED

        return job
    except Exception as e:
        logger.exception(f"Job with run_worker {job.job_id} failed catastrophically.")
        # TODO: Handel errors in execution and publication



