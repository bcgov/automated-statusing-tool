#main to run the fastapi backend connection to the ast_engine
import json
import logging
from pathlib import Path
from typing import Literal

from contextlib import asynccontextmanager

import redis
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, status

from .database import create_job, create_table, get_jobs
from shared_models.models import CreateJob, JobQueueItem, JobStatus

logger = logging.getLogger("ast_api.main")

redis_client = redis.Redis(host="localhost", port=6379, decode_responses=True)


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
):
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
    if upload_file is not None:
        upload_content = await upload_file.read()
        upload_metadata = {
            "filename": upload_file.filename,
            "size_bytes": len(upload_content),
        }

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
    job_id = create_job(job)

    queue_item = JobQueueItem(
        job_id=str(job_id),
        name=job.name,
        email=job.email,       
        region=job.region.value if hasattr(job.region, "value") else str(job.region),
        source=job.source,
        status=job.status or JobStatus.QUEUED,
    )

    queue.rpush("jobs_queue", json.dumps(queue_item.model_dump(mode="json")))

    return {
        "job": job.model_dump(mode="json"),
        "item": queue_item.model_dump(mode="json"),
        "upload": upload_metadata,
    }


@app.get("/jobs")
def read_jobs():
    return get_jobs()


@app.get(
    "/api/jobs",
    response_model=list[JobQueueItem],
    status_code=status.HTTP_200_OK,
)
def get_whole_queue(queue: redis.Redis = Depends(lambda: redis_client)):
    raw_jobs = [json.loads(item) for item in queue.lrange("jobs_queue", 0, -1)]
    return [JobQueueItem(**job) for job in raw_jobs]


@app.get(
    "/api/jobs/{job_id}",
    response_model=JobQueueItem,
    status_code=status.HTTP_200_OK,
)
def get_job_by_id(job_id: str, queue: redis.Redis = Depends(lambda: redis_client)):
    raw_jobs = [json.loads(item) for item in queue.lrange("jobs_queue", 0, -1)]
    job = next((job for job in raw_jobs if job["job_id"] == job_id), None)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return JobQueueItem(**job)


@app.get("/api/debug/queue")
def debug_queue(queue: redis.Redis = Depends(lambda: redis_client)):
    items = [json.loads(item) for item in queue.lrange("jobs_queue", 0, -1)]
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
