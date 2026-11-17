import os
import logging
import tempfile
from pathlib import Path
import geopandas as gpd
from datetime import datetime, UTC
from uuid import UUID
from enum import StrEnum
from typing import Optional, Any, Iterable
from pydantic import BaseModel

from ast_engine.core.aoi import AOIBuilder, AOIBuildRequest, AOIRequest
from ast_engine.core.aoi.exceptions import AOIError, AOIValidationError
from ast_engine.core.execution import run_analysis, build_tasks
from ast_engine.core.results import AstResults
from ast_engine.core.data_adapters.oracle import OracleConnection
from ast_engine.utils.diagnostics import DiagnosticTracker
from ast_engine.storage.publisher import ResultsPublisher
from ast_engine.storage import create_results_writer, created_date, JobStorageContext
from ast_engine.storage.models import OperatorArtifact
from ast_engine.config.settings import Settings

logger = logging.getLogger(__name__)
settings = Settings()

# What the user is told when a job fails for a reason that is ours, not theirs.
# The cause is in the worker log; an internal error can name tables, paths or hosts.
INTERNAL_ERROR_MESSAGE = "The job could not be run. See the worker log for details."

class JobStatus(StrEnum):
    QUEUED = "Queued"
    PROCESSING = "Processing"
    PUBLISHING = "Publishing"
    COMPLETED = "Completed"
    FAILED = "Failed"

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
    # why the job failed, in words a user can act on; None unless status is FAILED
    error: Optional[str] = None


def open_oracle_connection(settings: Settings) -> Optional[OracleConnection]:
    """Open the BCGW connection for a run, or return None when no login is configured.

    A run over file or GeoParquet datasets needs no database, so a worker with no
    BCGW login in its settings can still run those. A job that does need BCGW then
    fails inside the run with a message saying so (see run_analysis), rather than
    every job failing here before it starts.

    The caller owns the connection it gets back and must close it.
    """
    configured = all((
        settings.oracle_user,
        settings.oracle_password,
        settings.oracle_host,
        settings.oracle_database,
    ))
    if not configured:
        logger.info("No BCGW login configured; running without a database connection")
        return None

    return OracleConnection(
        username=settings.oracle_user,
        password=settings.oracle_password.get_secret_value(),
        hostname=f'{settings.oracle_host}:{settings.oracle_port}/{settings.oracle_database}',
    )


def _job_work_dir(job_id: UUID) -> Path:
    """The folder a job's files are written to before they are published.

    Under settings.temp_dir when it is set, otherwise under the system's
    temporary folder, so publishing works without any configuration.
    """
    root = Path(settings.temp_dir) if settings.temp_dir else Path(tempfile.gettempdir()) / "ast_engine"
    return root / str(job_id)


def publish_results(job: AstJob, ast_results: AstResults):
    # Publishes AstResults to local disk storage or S3

    logging.debug("Publish [job-id: %s]: Started",job.job_id)
    job.status = JobStatus.PUBLISHING

    # hey -- AstResults is a Pydantic model, so we can serialize it to JSON directly
    output_dir = _job_work_dir(job.job_id)
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
    # The storage path is filed by day; created_date() takes the day out of the
    # job's timestamp the same way for whoever reads the results back.
    storage_context = JobStorageContext(job_id=job.job_id,created_date=created_date(job.created_at))
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

def run_worker(
    job: AstJob,
    publish: bool = False,
    oracle_connection: Optional[OracleConnection] = None,
) -> AstJob:
    """Run one job through the engine and return it with its outcome recorded.

    Executes ast_engine and, with publish=True, publishes the results using the
    storage settings in ast_engine.config.settings.

    The job always comes back, whether it ran or not:
      - status COMPLETED when the analysis ran (and, with publish=True, its
        results were published);
      - status FAILED, with job.error saying why, when it did not.
    Nothing is raised, so one bad job never stops a worker that is working
    through a queue. The full error is in the log either way.

    oracle_connection: pass an open connection to have the run use it - the
    caller then still owns it and closes it. Leave it out and the worker opens
    one from its settings (when a BCGW login is configured) and closes it again.
    """
    logger.info("Worker Processing [job-id:%s]", job.aoi_id)
    if publish is True:
        logger.info("Worker Processing [job-id:%s] -- Publication On: %s storage", job.aoi_id,settings.storage_type)
    else:
        logger.info("Worker Processing [job-id:%s] -- Publication OFF", job.aoi_id)
        
    job.status = JobStatus.PROCESSING

    # Only close a connection this function opened itself.
    owns_connection = oracle_connection is None
    try:
        # Create database connection
        if owns_connection:
            oracle_connection = open_oracle_connection(settings)

        # Form the AOI
        # TODO: Is from features what we want to use here?Coordinate with API
        gdf = gpd.GeoDataFrame.from_features(job.aoi["features"])

        logging.info("Setting AOI area of interest to EPSG:4326")
        gdf.crs ="EPSG:4326"
        logger.debug("AOI GeoDataFrame has crs %s", str(gdf.crs))
        
        request = AOIRequest(aoi_id=job.aoi_id, name=job.aoi_name, target_crs= settings.system_crs)
        built = AOIBuilder().build_from_request(AOIBuildRequest(spec=request, raw_gdf=gdf))
        # Stop on AOI validation errors, as the old from_gdf did; log the warnings.
        # TODO: agree the worker's rule for AOI validation issues with the team
        for issue in built.warnings:
            logger.warning("AOI warning %s: %s", issue.code, issue.message)
        if built.has_errors:
            raise AOIValidationError("; ".join(f"{issue.code}: {issue.message}" for issue in built.errors))
        aoi = built.aoi

        tasks = build_tasks(job.registries)
        tracker = DiagnosticTracker()
        # engage engine
        ast_results = run_analysis(
            aoi=aoi,
            tasks=tasks,
            job_id=job.job_id,
            oracle_connection=oracle_connection,
            tracker=tracker,
            settings=None
        )
        # TODO: what to do with tracker info?

        # option pubilsh results
        if publish is True:
            publish_results(job=job, ast_results=ast_results)
        job.status = JobStatus.COMPLETED
    except AOIError as e:
        # The area of interest itself is the problem (no usable geometry, too
        # small, too large...). The message says what is wrong with the shape,
        # so it is passed on for the user to act on.
        logger.exception("Job %s failed: the AOI could not be used.", job.job_id)
        job.status = JobStatus.FAILED
        job.error = f"The area of interest could not be used: {e}"
    except Exception:
        # Anything else is ours, not the user's. The details stay in the log -
        # an internal error can name tables, paths or hosts.
        logger.exception(f"Job with run_worker {job.job_id} failed catastrophically.")
        job.status = JobStatus.FAILED
        job.error = INTERNAL_ERROR_MESSAGE
    finally:
        if owns_connection and oracle_connection is not None:
            oracle_connection.close()

    return job
