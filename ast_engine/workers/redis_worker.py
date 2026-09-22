# ast_engine/workers/redis_worker.py
# this worker polls redis for jobs and pushes the AstJob to worker
# this is an entry point

import logging
import redis
from pydantic import ValidationError
from ast_engine.config.settings import Settings
from worker import run_worker, AstJob, JobStatus
from ast_engine.config.logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

def main():
    settings = Settings()
    redis_host= settings.redis_host
    redis_port = settings.redis_port
    redis_database = settings.redis_database

    redis_client = redis.Redis(host=redis_host, port=redis_port, db=redis_database)
    queue_name = settings.job_queue

    logger.info(f"Listening for jobs on Redis queue: {queue_name}")

    while True:
        # TODO: Look at using a job status like below examples or can we update using the job.status
        # example api use redis.rpush("ast:pending", job.model_dump_json())
        # example worker use 
        # message = redis.brpoplpush("ast:pending", "ast:processing", timeout=0)

        # Blocking pop from the Redis queue 
        # Payload expected to be a JSON string with job details
        queue, message = redis_client.blpop(queue_name)
    
        if not message:
            continue
        queue, message = redis_client.blpop(queue_name)

        try:
            job = AstJob.model_validate_json(message)
        except ValidationError as e:
            logger.error("Invalid queue message: %s", e)
            continue
        try:
            ast_job = run_worker(job=job, publish=False)
            ast_job.status = JobStatus.COMPLETED
            logging.info("Completed job-id: %s",job.job_id)
            return ast_job
        except Exception as e:
            # add ast job info
            logger.exception("Exception while running(runworker) job-id: %s status: %s \n %s", job.job_id, job.status, e)
        
if __name__ == "__main__":
    main()