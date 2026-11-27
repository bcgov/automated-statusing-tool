# ast_engine/entry/queue_worker.py

import os
import sys
import signal
import logging
from rq import Worker, Queue, Connection
from redis import Redis


from ast_engine.config.logging_config import setup_logging
from ast_engine.config.settings import Settings
from shared_models.models import JobQueueItem
from shared_models.engine import AstEngineJob
from worker import run_worker
settings = Settings()
setup_logging()
# Configure logging
logger = logging.getLogger(__name__)

class AstEngineWorker(Worker):
    """
    Subclass of RQ Worker that handles graceful shutdowns. 
    When OpenShift sends SIGTERM, it stops accepting *new* jobs 
    and finishes the currently active job before exiting.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.handle_signals = True
        self._shutdown_requested = False

        # Trap termination signals from OpenShift/Kubernetes
        signal.signal(signal.SIGTERM, self.request_shutdown)
        signal.signal(signal.SIGINT, self.request_shutdown)

    def request_shutdown(self, signum, frame):
        logger.info(f"Received signal {signum}. Shutting down gracefully after current job finishes...")
        self._shutdown_requested = True
        # Tell RQ to stop fetching new jobs from the queue
        self.set_state('stopped')

def process_queue_job(job_data: dict):
    """
    RQ entry point wrapper that unpacks dictionary data into an AstJob 
    and executes the analysis pipeline.
    """
    publish = job_data.pop("publish", False)
    
    # Reconstruct the AstJob Pydantic model from dict
    job = JobQueueItem(**job_data)
    
    logger.info("RQ Worker picked up job-id: %s", job.job_id)

    # TODO: Saturate AstEngineJob from db
    job = AstEngineJob(job.job_id,
            registries=None, 
            created_at= None,
            user=None, 
            aoi_id=None, 
            aoi_name=None, 
            aoi=None, 
            aoi_options=None, 
            status=None
        )

    publish = False
    # Execute your existing worker logic
    completed_job = run_worker(job, publish=publish)
    
    return completed_job.status

def main():
    
    queue_name = settings.job_queue

    logger.info(f"Connecting to Valkary/Redis at {settings.redis_host}:{settings.redis_port}/{str(settings.redis_database)}...")
    redis_client = Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        db=settings.redis_database,
    )

    # Verify connection
    try:
        redis_client.ping()
        logger.info("Successfully connected to Valkey/Redis.")
    except Exception as e:
        logger.error(f"Failed to connect to Valkey/Redis: {e}")
        sys.exit(1)

    with Connection(redis_client):
        # Listen to the designated queue using our custom AstEngineWorker class
        queues = [Queue(queue_name)]
        worker = AstEngineWorker(queues)
        
        logger.info(f"Starting worker listening on queue: {queue_name}")
        worker.work(burst=False)

if __name__ == "__main__":
    main()