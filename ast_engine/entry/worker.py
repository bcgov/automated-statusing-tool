import logging
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Optional, Any, Iterable
from uuid import UUID
import geopandas as gpd
from pydantic import BaseModel

from ast_engine.config.settings import Settings
from ast_engine.config.validation.startup import create_aoi_builder
from ast_engine.core.aoi import AOIBuildRequest, AOIRequest
from ast_engine.core.aoi.exceptions import AOIValidationError
from ast_engine.core.data_adapters.oracle import OracleConnection
from ast_engine.core.execution import build_tasks, run_analysis
from ast_engine.core.results import AstResults
from ast_engine.storage import JobStorageContext, create_results_writer
from ast_engine.storage.models import OperatorArtifact
from ast_engine.storage.publisher import ResultsPublisher
from ast_engine.utils.diagnostics import DiagnosticTracker

# Shared models
from shared_models.mappings import region_to_org_unit
from shared_models.models import Regions


logger = logging.getLogger(__name__)
settings = Settings()


class JobStatus(StrEnum):
    QUEUED = "Queued"
    PROCESSING = "Processing"
    PUBLISHING = "Publishing"
    COMPLETED = "Completed"
    FAILED = "Failed"


# Payload structure TODO: ensure aoi crs is same as api and frontend
class AstJob(BaseModel):
    job_id: UUID
    region: Regions
    registries: Iterable[tuple[str, Any]]
    created_at: Optional[str] = None
    user: str
    aoi_id: str
    aoi_name: str
    aoi: dict[str, Any]  # gdf.to_json()
    status: Optional [JobStatus]


def publish_results(job: AstJob, ast_results: AstResults):
    # Publishes AstResults to local disk storage or S3

    logger.debug("Publish [job-id: %s]: Started", job.job_id)
    job.status = JobStatus.PUBLISHING

    # hey -- AstResults is a Pydantic model, so we can serialize it to JSON directly
    output_dir = Path(settings.temp_dir) / str(job.job_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_results_file = output_dir / "raw_results.json"
    raw_results_file.write_text(ast_results.model_dump_json())

    # catalog the operator artifacts
    operator_outputs = []
    for dataset_group in ast_results.results:
        for part in dataset_group.parts:
            result = part.result
            if result.spatial_link:
                operator_output = OperatorArtifact(registry=result.registry,operator=result.operator_type.value,dataset_name=dataset_group.dataset_name,path=result.spatial_link,part_id=part.aoi_part_id)
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
        operator_outputs=operator_outputs,
        # Include other optional paths as they become available:
        # extracted_gpkg=..., 
        # aoi_geojson=...,
    )
    logger.debug("Publish [job-id: %s]: Completed", job.job_id)
    return {"job": job, "artifacts": artifacts}


def run_worker(
    job: AstJob,
    publish: bool = False,
):
    # executes ast_engine and optionally publishes using storage settings in ast_engine.config.settings
    # returns job with updated status
    logger.info("Worker Processing [job-id:%s]", job.aoi_id)
    if publish is True:
        logger.info("Worker Processing [job-id:%s] -- Publication On: %s storage", job.aoi_id,settings.storage_type)
    else:
        logger.info("Worker Processing [job-id:%s] -- Publication OFF", job.aoi_id)
        
    job.status = JobStatus.PROCESSING

    conn = None

    try:
        # Create database connection
        conn = OracleConnection(username=settings.oracle_user,
                                password=settings.oracle_password.get_secret_value(),
                                hostname=f'{settings.oracle_host}:{settings.oracle_port}/{settings.oracle_database}'
                                )
        # Form the AOI
        # TODO: Is from features what we want to use here?Coordinate with API
        gdf = gpd.GeoDataFrame.from_features(job.aoi["features"])

        logger.info("Setting AOI area of interest to EPSG:4326")
        gdf.crs = "EPSG:4326"
        logger.debug("AOI GeoDataFrame has crs %s", str(gdf.crs))

        # TODO: Review whether the AOIBuilder should be created once per worker or per job.
        # If per job, then this is fine. If per worker, then move this to the worker startup code.
        # This would require establishing a connection to Oracle once per worker, which may be more efficient.
        # TODO: Investigate whethere we should pass the adapters vs the connection to the AOIBuilder.
        # Required for validation reference layers, which may access BCGW.
        aoi_builder = create_aoi_builder(settings, profile="runtime", connection=conn)

        required = aoi_builder.validator.required_spatial_parameters

        # Pass the region and other validation parameters for the job to the AOIBuilder,
        # so it can be used in validation checks, if required by the AOIBuilder's validator.
        validation_parameters = None

        if "expected_unit_ids" in required:
            validation_parameters = {
                "expected_unit_ids": (
                    region_to_org_unit(job.region),
                ),
            }

        # TODO: Consider whether the AOIRequest should include the validation parameters,
        # or if they should be passed only to the AOIBuilder as they are job specific.
        # This will depend on whether the AOIBuilder is at the worker or job level.
        request = AOIRequest(
            aoi_id=job.aoi_id,
            name=job.aoi_name,
            target_crs=settings.system_crs,
            validation_parameters=validation_parameters,
        )

        built = aoi_builder.build_from_request(
            AOIBuildRequest(spec=request, raw_gdf=gdf),
        )

        # Stop on AOI validation errors, as the old from_gdf did; log the warnings.
        # TODO: agree the worker's rule for AOI validation issues with the team
        for issue in built.warnings:
            logger.warning(
                "Job %s | AOI %s | %s: %s",
                job.job_id, job.aoi_id, issue.code, issue.message,
            )

        # AOI validation error findings are not exceptions to be handled.
        # Log the errors and return the failed job with the status and do
        # not raise.
        if built.has_errors:
            job.status = JobStatus.FAILED
            for issue in built.errors:
                logger.error(
                    "Job %s | AOI %s rejected | %s | subject=%s: %s",
                    job.job_id, job.aoi_id, issue.code, issue.subject_id, issue.message,
                )

            # TODO: establish pathway for AOI valdiation errors to propogate
            # Likely return them as part of the AstJob. 
            return job

        # AOI validated. Proceed to analysis tasks.
        aoi = built.aoi

        tasks = build_tasks(job.registries)
        tracker = DiagnosticTracker()
        # engage engine
        ast_results = run_analysis(
            aoi=aoi,
            tasks=tasks,
            job_id=job.job_id,
            oracle_connection=conn,
            tracker=tracker,
            settings=settings,
        )
        # TODO: what to do with tracker info?

        # option pubilsh results
        if publish is True:
            publish_results(job=job, ast_results=ast_results)
        job.status = JobStatus.COMPLETED

        return job
    
    except Exception:
        job.status = JobStatus.FAILED
        raise
    finally:
        if conn is not None:
            conn.close()
        # TODO: Handle errors in execution and publication