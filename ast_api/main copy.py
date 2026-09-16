# #main to run the fastapi backend connection to the ast_engine
# import json
# import logging

# import redis
# from fastapi import Depends, FastAPI, HTTPException, status
# from ast_api.models import CreateJobRequest, JobResponse, JobQue
# from ast_engine.config.logging_config import setup_logging


# '''
# This is the main entry point for the FastAPI backend connection to the AST engine. It sets up logging, 
# initializes a Redis client, and defines API endpoints for managing jobs in the queue. 

# The endpoints allow users to create new jobs, retrieve job details, and list all jobs in the queue. 
# The job data is stored in Redis, and the API uses Pydantic models for data validation and serialization.

# Payload = references the json FROM the api 

# Redis endpoints 
# (Post Que Item) Payload -> Que
# (Get Que Item) Que -> Return

# Database endpoints 
# (Post Job) Payload -> Database
# (Get Job) Database -> Return

# '''


# setup_logging()
# logger = logging.getLogger("ast_api.main")
# import logging
# from ast_engine.config.logging_config import setup_logging

# setup_logging()
# logger = logging.getLogger("ast_api")


# #set up Redis client e
# redis_client=redis.Redis(host='localhost', port=6379, decode_responses=True)

# ###JORD!!!
# #Everything below this might need to be CHANGED :D

# #need to change this? 
# def get_db(): 
#     yield redis_client

# app = FastAPI()


# # Helper function to avoid code duplication
# def _get_all_jobs(db: redis.Redis) -> list[dict]:
#     raw_jobs = db.lrange("jobs_queue", 0, -1)
#     return [json.loads(j) for j in raw_jobs]

# """Post a new item to the queue. This will create a new job in the Redis queue and return the job details."""
# @app.post(
#     "/api/queue",
#     response_model=JobQue,
#     status_code=status.HTTP_201_CREATED,
# )

# @app.post(
#     "api/jobs", 
#     response_model=JobResponse,
# )
# def create_que_item(job: CreateJobRequest, db: redis.Redis = Depends(get_db)):
#     logger.info("Creating job for AOI %s in region %s", job.area_of_interest, job.region.value)
#     jobs = _get_all_jobs(db)

#     try:
#         existing_ids = [
#             int(j["job_id"]) for j in jobs if isinstance(j, dict) and "job_id" in j and str(j["job_id"]).isdigit()
#         ]
#         new_id = max(existing_ids, default=0) + 1

#         new_job = {
#             "job_id": str(new_id),
#             "region": job.region.value,
#             "area_of_interest": job.area_of_interest,
#             "crown_file_number": job.crown_file_number,
#             "disposition_number": job.disposition_number,
#             "parcel_number": job.parcel_number,
#             "output_directory": job.output_directory,
#             "status": "Pending",
#         }

#         # Persist directly into the Redis queue
#         db.rpush("jobs_queue", json.dumps(new_job))
#         logger.info("Job created successfully: %s", new_job["job_id"])
#         return JobResponse.model_validate(new_job)
#     except Exception:
#         logger.exception("Failed to create job")
#         raise


# @app.get("/api/jobs", response_model=list[JobResponse])
# def get_jobs(db: redis.Redis = Depends(get_db)):
#     logger.info("Listing all jobs")
#     return [JobResponse.model_validate(job) for job in _get_all_jobs(db)]


# @app.get("/api/jobs/{job_id}", response_model=JobResponse)
# def get_job(job_id: str, db: redis.Redis = Depends(get_db)):
#     logger.info("Looking up job %s", job_id)
#     jobs = _get_all_jobs(db)

#     for job in jobs:
#         if str(job.get("job_id")) == str(job_id):
#             logger.info("Job %s found", job_id)
#             return JobResponse.model_validate(job)
#     logger.warning("Job %s not found", job_id)
#     raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")



# @app.get("/api/que", response_model=JobQue)
# def get_payload(job_id: str, db: redis.Redis = Depends(get_db)):
#     logger.info("Looking up payload %s", job_id)
#     # fill this out 
