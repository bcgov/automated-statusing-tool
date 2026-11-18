import os
import logging
import tempfile
from pathlib import Path
import geopandas as gpd
from datetime import date, datetime, UTC
from uuid import UUID
from enum import StrEnum
from typing import Optional, Any, Iterable
from pydantic import BaseModel

from ast_engine.core.aoi import AOIBuilder, AOIBuildRequest, AOIRequest
from ast_engine.core.aoi.exceptions import AOIError, AOIValidationError
from ast_engine.core.execution import run_analysis, build_tasks
from ast_engine.core.results import AstResults
from ast_engine.core.data_adapters.oracle import (
    InactiveTenure,
    OracleConnection,
    fetch_applicant_name,
    fetch_inactive_tenures,
    fetch_received_dates,
    fetch_tenure_details,
)
from ast_engine.utils.diagnostics import DiagnosticTracker
from ast_engine.reporting import (
    OVERVIEW_MAP_NAME,
    MapOutput,
    ReportHeader,
    TenureFacts,
    aoi_part_names,
    build_crown_land_status,
    build_dataset_reports,
    build_map_layers,
    generate_html_maps,
    write_status_report,
)
from ast_engine.storage.publisher import ResultsPublisher
from ast_engine.storage import create_results_writer, created_date, JobStorageContext
from ast_engine.storage.models import MapArtifact, OperatorArtifact
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
    # make an HTML map per dataset, plus an overview map, and publish them
    generate_maps: bool = False
    # publish the features each dataset matched, as GeoPackages
    export_overlap_results: bool = False
    # leave the Conflicts & Constraints tab (Tab 3) and its maps out of the job
    suppress_tab3: bool = False
    # What the status was asked for, printed at the top of the status report.
    region: Optional[str] = None
    crown_file_number: Optional[str] = None
    disposition_number: Optional[str] = None
    parcel_number: Optional[str] = None
    # The name, among `registries`, of the Tab 1 registry. Its datasets fill the
    # Crown Land Status tab of the report and are left off the Conflicts &
    # Constraints tab. None when the job runs no Tab 1 registry.
    tab1_registry: Optional[str] = None


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
        client_lib_dir=settings.oracle_client_lib_dir,
    )


def _job_work_dir(job_id: UUID) -> Path:
    """The folder a job's files are written to before they are published.

    Under settings.temp_dir when it is set, otherwise under the system's
    temporary folder, so publishing works without any configuration.
    """
    root = Path(settings.temp_dir) if settings.temp_dir else Path(tempfile.gettempdir()) / "ast_engine"
    return root / str(job_id)


def _run_settings(job: AstJob) -> Optional[Settings]:
    """The settings one job's analysis runs with, or None to use the defaults.

    The features a dataset matched are only saved when record_spatial is on.
    Maps are drawn from those saved features, and exporting the overlap results
    publishes them, so a job that asks for either has them saved - into the
    job's own work folder - whatever the worker's own setting is.
    """
    if not (job.generate_maps or job.export_overlap_results):
        return None
    return settings.model_copy(update={
        "record_spatial": True,
        "temp_dir": str(_job_work_dir(job.job_id) / "spatial"),
    })


def _generate_maps(job: AstJob, aoi, tasks, ast_results: AstResults) -> list[MapOutput]:
    """Make the job's HTML maps and return them; an empty list if it cannot.

    Maps are an extra on top of the results. If they cannot be made the job
    still completes with its results, and the reason is in the log.
    """
    try:
        return generate_html_maps(
            aoi=aoi.gdf,
            layers=build_map_layers(tasks, ast_results),
            out_dir=_job_work_dir(job.job_id) / "maps",
        )
    except Exception:
        logger.exception("Could not create the maps for job %s; publishing without them", job.job_id)
        return []


def _map_link(job: AstJob, map_name: str) -> str:
    """The link the status report uses for one of the job's maps.

    Through the API when its public address is configured, so the link works
    from a downloaded report. Otherwise relative to the report, which works in a
    copy of the job's published folder.
    """
    if settings.api_public_url:
        return f"{settings.api_public_url.rstrip('/')}/api/jobs/{job.job_id}/maps/{map_name}"
    return f"maps/{map_name}.html"


def _tenure_facts(job: AstJob, oracle_connection: Optional[OracleConnection]) -> TenureFacts:
    """Read what TANTALIS says about the job's Crown land file, for the report.

    Empty for an uploaded AOI, which has no file, and when there is no BCGW
    connection. If the lookup fails the report is still written, with those
    lines blank and the reason in the log.

    The applicant's name is personal information: it goes into the report and
    is never logged.
    """
    if oracle_connection is None or not (job.crown_file_number and job.disposition_number):
        return TenureFacts()
    try:
        cursor = oracle_connection.cursor
        details = {}
        if job.parcel_number:
            details = fetch_tenure_details(
                cursor, job.crown_file_number, job.disposition_number, job.parcel_number,
            )
        return TenureFacts(
            applicant_name=fetch_applicant_name(cursor, job.disposition_number),
            received_dates=tuple(fetch_received_dates(cursor, job.disposition_number)),
            details=details,
        )
    except Exception:
        logger.exception("Could not read the TANTALIS file details for job %s", job.job_id)
        return TenureFacts()


def _inactive_tenures(job: AstJob, aoi, oracle_connection: Optional[OracleConnection]) -> Optional[list[InactiveTenure]]:
    """Read the inactive Crown land tenures on the AOI, for the report.

    Returns None when they could not be read - there is no BCGW connection, or
    the lookup failed. The Status of Conflict tab then says the AOI was not
    evaluated, which is not the same as having no inactive tenures.
    """
    if oracle_connection is None:
        return None
    try:
        return fetch_inactive_tenures(oracle_connection.connection, oracle_connection.cursor, aoi.gdf)
    except Exception:
        logger.exception("Could not read the inactive tenures for job %s", job.job_id)
        return None


def _write_report(
    job: AstJob,
    registries: list[tuple[str, Any]],
    aoi,
    tasks,
    ast_results: AstResults,
    maps: list[MapOutput],
    oracle_connection: Optional[OracleConnection],
) -> Optional[Path]:
    """Write the job's status report (the Excel workbook) and return its path.

    Returns None if it cannot be written. Like the maps, the report is built on
    top of the results: the job still completes with its results without it,
    and the reason is in the log.
    """
    try:
        run_date = date.fromisoformat(created_date(job.created_at))
        links = {item.name: _map_link(job, item.name) for item in maps}
        header = ReportHeader(
            report_date=run_date,
            region=job.region or "",
            aoi_name=job.aoi_name,
            crown_file_number=job.crown_file_number,
            disposition_number=job.disposition_number,
            parcel_number=job.parcel_number,
            registries=tuple(name for name, _ in registries),
            part_names=aoi_part_names(aoi.gdf),
            overview_map_link=links.get(OVERVIEW_MAP_NAME),
        )
        datasets = build_dataset_reports(
            tasks,
            ast_results,
            map_links={item.key: links[item.name] for item in maps if item.key},
            # Tab 1's datasets fill the Crown Land Status tab instead.
            exclude_registries=[job.tab1_registry] if job.tab1_registry else [],
        )
        crown_land_status = build_crown_land_status(
            tasks,
            ast_results,
            tab1_registry=job.tab1_registry or "",
            run_date=run_date,
            run_by=job.user,
            region=job.region or "",
            crown_file_number=job.crown_file_number,
            disposition_number=job.disposition_number,
            tenure=_tenure_facts(job, oracle_connection),
        )
        return write_status_report(
            _job_work_dir(job.job_id) / "status-report.xlsx",
            header=header,
            datasets=datasets,
            crown_land_status=crown_land_status,
            inactive_tenures=_inactive_tenures(job, aoi, oracle_connection),
            include_conflicts=not job.suppress_tab3,
        )
    except Exception:
        logger.exception("Could not write the status report for job %s; publishing without it", job.job_id)
        return None


def publish_results(
    job: AstJob,
    ast_results: AstResults,
    maps: Optional[list[MapOutput]] = None,
    publish_spatial: bool = True,
    report: Optional[Path] = None,
):
    # Publishes AstResults to local disk storage or S3
    #
    # maps: the job's HTML maps, published alongside the results.
    # report: the job's status report (the Excel workbook).
    # publish_spatial: False leaves the saved features (GeoPackages) unpublished -
    # for a job that had them saved only to draw its maps from.

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
            if publish_spatial and result.spatial_link:
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
        operator_outputs=operator_outputs,
        map_outputs=[MapArtifact(name=item.name, title=item.title, path=item.path) for item in maps or []],
        report_xlsx=report,
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

        # Read into a list once: the job's registries may be handed over as a
        # one-pass iterable, and both the run and the report go through them.
        registries = list(job.registries)
        tasks = build_tasks(registries)
        tracker = DiagnosticTracker()
        # engage engine
        ast_results = run_analysis(
            aoi=aoi,
            tasks=tasks,
            job_id=job.job_id,
            oracle_connection=oracle_connection,
            tracker=tracker,
            settings=_run_settings(job)
        )
        # TODO: what to do with tracker info?

        # The maps show what the Tab 3 datasets found, so there are none to
        # make for a job that leaves Tab 3 out.
        make_maps = job.generate_maps and not job.suppress_tab3
        maps = _generate_maps(job, aoi, tasks, ast_results) if make_maps else []

        # option pubilsh results
        if publish is True:
            publish_results(
                job=job,
                ast_results=ast_results,
                maps=maps,
                report=_write_report(job, registries, aoi, tasks, ast_results, maps, oracle_connection),
                # The saved features are published when the job asked for them, or
                # when the worker is set to keep them for every job.
                publish_spatial=job.export_overlap_results or settings.record_spatial,
            )
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
