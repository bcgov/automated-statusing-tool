#main to run the fastapi backend connection to the ast_engine
import json
import logging

import redis
from rq import Queue
from fastapi import Depends, FastAPI, HTTPException, status
from shared_models.models import CreateJob, JobQueueItem, JobPayload
from ast_api.database import create_table, create_job, get_jobs
from ast_api.config.logging_config import setup_logging
from ast_api.utils import _get_all_jobs
from contextlib import asynccontextmanager



'''
This is the main entry point for the FastAPI backend connection to the AST engine. It sets up logging, 
initializes a Redis client, and defines API endpoints for managing jobs in the queue. 

The endpoints allow users to create new jobs, retrieve job details, and list all jobs in the queue. 
The job data is stored in Redis, and the API uses Pydantic models for data validation and serialization.

Payload = references the json FROM the api 

Redis endpoints 
(Post Queue Item) Payload -> Queue
(Get Queue Item) Queue -> Return

Database endpoints 
(Post Job) Payload -> Database
(Get Job) Database -> Return

'''


setup_logging()
logger = logging.getLogger("ast_api.main")
import logging
from ast_engine.config.logging_config import setup_logging

setup_logging()
logger = logging.getLogger("ast_api")


#set up Redis client e
redis_client=redis.Redis(host='localhost', port=6379, decode_responses=True)


app = FastAPI()

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Creating database tables...")
    create_table()
    yield

app = FastAPI(lifespan=lifespan)


'''Post a new item to the queue AND database. This will create a new job in the Redis queue and sql lite and return the job details.'''
@app.post("/api/payload_dump", status_code=status.HTTP_201_CREATED)
def create_job_in_queue_and_db(
    request: JobPayload,
    queue: redis.Redis = Depends(lambda: redis_client),
):
    job_id = f"job_{len(_get_all_jobs(queue)) + 1}"

    job_data = request.job.model_dump()
    job_item = request.item.model_dump()

    job_data["job_id"] = job_id
    job_item["job_id"] = job_id

    create_job(CreateJob(**job_data))
    queue.rpush("jobs_queue", json.dumps(job_item))

    return {
        "job": job_data,
        "item": job_item,
    }




#this is for sql lite db 
@app.get("/jobs")
def read_jobs():
    return get_jobs()
#this is for debugging rq

@app.get(
    "/api/jobs",
    response_model=list[JobQueueItem],
    status_code=status.HTTP_200_OK,
)
def get_all_jobs(queue: redis.Redis = Depends(lambda: redis_client)):
    jobs = _get_all_jobs(queue)
    return [JobQueueItem(**job) for job in jobs]

@app.get(
    "/api/jobs/{job_id}",
    response_model=JobQueueItem,
    status_code=status.HTTP_200_OK,
)
def get_job_by_id(job_id: str, queue: redis.Redis = Depends(lambda: redis_client)):
    jobs = _get_all_jobs(queue)
    job = next((job for job in jobs if job["job_id"] == job_id), None)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return JobQueueItem(**job)

@app.get("/api/debug/queue")
def get_queue(
    queue: redis.Redis = Depends(lambda: redis_client)
):
    return [
        json.loads(item)
        for item in queue.lrange("jobs_queue", 0, -1)
    ]


#different debug
@app.get("/api/debug/queue")
def debug_queue(
    queue: redis.Redis = Depends(lambda: redis_client)
):
    return {
        "count": queue.llen("jobs_queue"),
        "items": [
            json.loads(item)
            for item in queue.lrange("jobs_queue", 0, -1)
        ]
    }