#main to run the fastapi backend connection to the ast_engine
import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from contextlib import asynccontextmanager

import redis
from fastapi import Depends, FastAPI, File, Form, HTTPException, Response, UploadFile, status
from fastapi.concurrency import run_in_threadpool

from .aoi_upload import AoiUploadError, read_aoi_upload
from .config.settings import Settings
from .database import create_job, create_table, get_jobs
from ast_engine.storage import (
    JobStorageContext,
    MANIFEST_KEY,
    MAP_ARTIFACT_PREFIX,
    RAW_RESULTS_KEY,
    ResultsStorageReader,
    create_results_reader,
    created_date,
    map_key,
)
from shared_models.job_store import JobStatusStore
from shared_models.models import CreateJob, JobQueueItem, JobStatus

logger = logging.getLogger("ast_api.main")

settings = Settings()

# The queue and the job status store both live in this Redis. The engine worker
# reads the same settings (host, queue name), which is what makes the two meet.
redis_client = redis.Redis(
    host=settings.redis_host,
    port=settings.redis_port,
    db=settings.redis_database,
    password=settings.redis_password.get_secret_value() if settings.redis_password else None,
    decode_responses=True,
)


# What a map's name may hold: the characters the engine names its maps with.
# Checked before a name from the URL is used to build a storage key.
MAP_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


def get_job_store() -> JobStatusStore:
    """The job status store, on the API's Redis client."""
    return JobStatusStore(redis_client, ttl_seconds=settings.job_status_ttl_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_table()
    yield


app = FastAPI(lifespan=lifespan)

@app.post("/api/jobs", status_code=status.HTTP_201_CREATED)
async def create_job_in_queue_and_db(
    name: str = Form(...),
    email: str = Form(...),
    region: str = Form(...),
    source: Literal["1", "2"] = Form(...),
    crown_file_number: str | None = Form(None),
    disposition_number: str | None = Form(None),
    parcel_number: str | None = Form(None),
    generate_maps: bool = Form(False),
    export_overlap_results: bool = Form(False),
    upload_file: UploadFile | None = File(None),
    queue: redis.Redis = Depends(lambda: redis_client),
    store: JobStatusStore = Depends(get_job_store),
):
    """Accept a statusing job, record it and queue it for the engine worker.

    The area of interest is settled here as far as the API can take it: an
    uploaded file is read into the shape the worker will run, so a file that
    cannot be used is refused now; a TANTALIS job is queued with its three
    identifiers, and the worker looks the parcel up in BCGW.
    """
    if source == "1" and not all((crown_file_number, disposition_number, parcel_number)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="TANTALIS source requires file, disposition, and parcel identifiers",
        )
    if source == "2" and upload_file is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Upload source requires an uploaded spatial file",
        )

    upload_metadata = None
    aoi = None
    if upload_file is not None:
        upload_content = await upload_file.read()
        if len(upload_content) > settings.max_upload_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"Uploaded file is larger than the {settings.max_upload_bytes} byte limit",
            )
        upload_metadata = {
            "filename": upload_file.filename,
            "size_bytes": len(upload_content),
        }
    if source == "2":
        # Reading a spatial file is slow, blocking work; keep it off the event loop.
        try:
            aoi = await run_in_threadpool(read_aoi_upload, upload_file.filename, upload_content)
        except AoiUploadError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc),
            ) from exc

    job = CreateJob(
        name=name,
        email=email,
        region=region,
        source=source,
        crown_file_number=crown_file_number,
        disposition_number=disposition_number,
        parcel_number=parcel_number,
        generate_maps=generate_maps,
        export_overlap_results=export_overlap_results,
    )
    # The job is known everywhere by this id - on the queue, in the status store
    # and in results storage. The engine identifies a job by UUID.
    job_id = str(uuid4())
    create_job(job, job_uuid=job_id)

    queue_item = JobQueueItem(
        job_id=job_id,
        name=job.name,
        email=job.email,       
        region=job.region.value if hasattr(job.region, "value") else str(job.region),
        source=job.source,
        status=job.status or JobStatus.QUEUED,
        crown_file_number=job.crown_file_number,
        disposition_number=job.disposition_number,
        parcel_number=job.parcel_number,
        aoi=aoi,
        generate_maps=job.generate_maps,
        export_overlap_results=job.export_overlap_results,
        created_at=datetime.now(UTC).isoformat(),
    )

    # The status record goes in first, so the job can be asked about from the
    # moment the worker is able to pick it up.
    store.save(queue_item)
    queue.rpush(settings.job_queue, queue_item.model_dump_json())

    return {
        "job": job.model_dump(mode="json"),
        "item": _without_aoi(queue_item).model_dump(mode="json"),
        "upload": upload_metadata,
    }


def _without_aoi(item: JobQueueItem) -> JobQueueItem:
    """A job as it is returned to the browser: everything but the shape.

    The AOI is carried for the worker. It can be large, and nothing in the
    browser reads it back from a job.
    """
    return item.model_copy(update={"aoi": None})


@app.get("/jobs")
def read_jobs():
    return get_jobs()


@app.get(
    "/api/jobs",
    response_model=list[JobQueueItem],
    status_code=status.HTTP_200_OK,
)
def get_whole_queue(queue: redis.Redis = Depends(lambda: redis_client)):
    """The jobs still waiting on the queue, oldest first."""
    raw_jobs = [json.loads(item) for item in queue.lrange(settings.job_queue, 0, -1)]
    return [_without_aoi(JobQueueItem(**job)) for job in raw_jobs]


@app.get(
    "/api/jobs/{job_id}",
    response_model=JobQueueItem,
    status_code=status.HTTP_200_OK,
)
def get_job_by_id(job_id: str, store: JobStatusStore = Depends(get_job_store)):
    """One job and its current status.

    Read from the job status store rather than the queue: a job leaves the
    queue as soon as the worker picks it up, and the worker records its
    progress and its outcome in the store.
    """
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


def _published_job_reader(job_id: str, store: JobStatusStore) -> ResultsStorageReader:
    """Return a reader over what the engine published for one completed job.

    A job that has not completed has nothing published: the error says where
    the job is, or why it failed.
    """
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if job.status == JobStatus.FAILED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job failed: {job.error}",
        )
    if job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job has no results yet (status: {job.status.value})",
        )

    # The worker files a job's results by its id and the day it was created;
    # created_date() gives both sides the same day.
    context = JobStorageContext(job_id=job.job_id, created_date=created_date(job.created_at))
    return create_results_reader(context)


@app.get("/api/jobs/{job_id}/results")
def get_job_results(job_id: str, store: JobStatusStore = Depends(get_job_store)):
    """The results the engine published for one completed job.

    Returned as the worker wrote them (an AstResults document).
    """
    reader = _published_job_reader(job_id, store)
    try:
        results = reader.get_text(RAW_RESULTS_KEY)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Results not found",
        ) from exc
    # Already JSON, as published - passed through without being parsed again.
    return Response(content=results, media_type="application/json")


@app.get("/api/jobs/{job_id}/maps")
def get_job_maps(job_id: str, store: JobStatusStore = Depends(get_job_store)):
    """The HTML maps published for one completed job, the overview first.

    Each item is a map's name, to fetch it by, and its title, to show. The list
    is empty for a job that was not asked for maps, or found nothing to map.
    """
    reader = _published_job_reader(job_id, store)
    try:
        manifest = json.loads(reader.get_text(MANIFEST_KEY))
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Results not found",
        ) from exc

    # The manifest lists every published artifact; the maps are the ones named
    # "map_<name>", in the order the engine wrote them.
    return [
        {
            "name": artifact_name.removeprefix(MAP_ARTIFACT_PREFIX),
            "title": (artifact.get("metadata") or {}).get("title", ""),
        }
        for artifact_name, artifact in manifest.get("artifacts", {}).items()
        if artifact_name.startswith(MAP_ARTIFACT_PREFIX)
    ]


@app.get("/api/jobs/{job_id}/maps/{map_name}")
def get_job_map(job_id: str, map_name: str, store: JobStatusStore = Depends(get_job_store)):
    """One of a completed job's HTML maps, as a page to open in the browser."""
    # The name goes into a storage key, so it is held to the characters a map
    # name can have before anything is read.
    if not MAP_NAME_PATTERN.fullmatch(map_name):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Map not found")

    reader = _published_job_reader(job_id, store)
    try:
        page = reader.get_text(map_key(map_name))
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Map not found",
        ) from exc
    return Response(content=page, media_type="text/html")


@app.get("/api/debug/queue")
def debug_queue(queue: redis.Redis = Depends(lambda: redis_client)):
    items = [json.loads(item) for item in queue.lrange(settings.job_queue, 0, -1)]
    return {
        "count": len(items),
        "items": items,
    }

@app.get("/api/results")
def get_results():
    '''
    Sample route for now -> returns a simple JSON results output object
    '''
    path = Path("ast_api/tests/data/results.json")

    with path.open(encoding="cp1252") as f:
        return json.load(f)
