#main to run the fastapi backend connection to the ast_engine
import json
import logging

from contextlib import asynccontextmanager

import redis
from fastapi import Depends, FastAPI, HTTPException, status

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
def create_job_in_queue_and_db(
    job: CreateJob,
    queue: redis.Redis = Depends(lambda: redis_client),
):
    job_id = create_job(job)

    queue_item = JobQueueItem(
        job_id=str(job_id),
        user=job.user,
        date=job.date,
        region=job.region.value if hasattr(job.region, "value") else str(job.region),
        aoi_id=job.aoi_id,
        aoi_name=job.aoi_name,
        output_directory=job.output_directory,
        status=job.status or JobStatus.QUEUED,
    )

    queue.rpush("jobs_queue", json.dumps(queue_item.model_dump(mode="json")))

    return {
        "job": job.model_dump(mode="json"),
        "item": queue_item.model_dump(mode="json"),
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