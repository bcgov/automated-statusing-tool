# ast_engine/entry/redis_worker.py
# this worker polls redis for jobs and pushes the AstJob to worker
# this is an entry point

"""
Redis worker: takes jobs off the job queue one at a time and runs them.

    uv run python -m ast_engine.entry.redis_worker

The API pushes a JobQueueItem onto the queue for every submitted job. For each
one this worker:

  1. marks the job Processing in the job status store;
  2. builds the AstJob (the region's registries and the area of interest);
  3. runs it and publishes the results to results storage;
  4. marks the job Completed, or Failed with the reason.

The status store is how the API tells the browser what became of a job, so a
job is always given a final status - even when it could not be read or run. One
job failing never stops the loop.
"""

import logging
import time
from datetime import datetime, UTC
from typing import Optional

import redis
from pydantic import ValidationError

from ast_engine.config.settings import Settings
from ast_engine.config.logging_config import setup_logging
from ast_engine.entry.job_builder import JobRequestError, build_ast_job
from ast_engine.entry.worker import INTERNAL_ERROR_MESSAGE, run_worker, open_oracle_connection
from shared_models.job_store import JobStatusStore
from shared_models.models import JobQueueItem, JobStatus

logger = logging.getLogger(__name__)

# How long one wait on the queue lasts before the worker asks again. It has to
# be shorter than the socket timeout: the Redis client gives up on a reply that
# takes longer than that, so a wait with no end stops an idle worker.
QUEUE_WAIT_SECONDS = 5
SOCKET_TIMEOUT_SECONDS = 30

# How long the worker holds off before asking again after Redis did not answer.
RETRY_DELAY_SECONDS = 5


def handle_message(
    message: str | bytes,
    store: JobStatusStore,
    settings: Settings,
) -> Optional[JobQueueItem]:
    """Run the job in one queue message and record what became of it.

    Returns the job's final status record, or None when the message could not
    be read as a job at all (there is then no job id to report against).

    Nothing is raised: whatever goes wrong is logged and written to the job's
    status record, so the loop in main() carries on to the next job.
    """
    try:
        item = JobQueueItem.model_validate_json(message)
    except ValidationError as e:
        # The input is left out of the log: a queue message holds a name and an email.
        logger.error("Invalid queue message: %s", e.errors(include_input=False))
        return None

    logger.info("Picked up job-id: %s", item.job_id)
    item = _record(store, item, status=JobStatus.PROCESSING)

    # One connection for the job: the TANTALIS lookup and the run share it.
    oracle_connection = None
    try:
        oracle_connection = open_oracle_connection(settings)
        job = build_ast_job(
            item,
            registry_dir=settings.registry_output_path,
            oracle_connection=oracle_connection,
        )
        job = run_worker(job=job, publish=True, oracle_connection=oracle_connection)
        # The worker's status names are the shared ones, value for value.
        status, error = JobStatus(job.status.value), job.error
    except JobRequestError as e:
        logger.warning("Job-id: %s cannot be run as submitted: %s", item.job_id, e)
        status, error = JobStatus.FAILED, str(e)
    except Exception:
        logger.exception("Exception while preparing job-id: %s", item.job_id)
        status, error = JobStatus.FAILED, INTERNAL_ERROR_MESSAGE
    finally:
        if oracle_connection is not None:
            oracle_connection.close()

    logger.info("Finished job-id: %s status: %s", item.job_id, status.value)
    return _record(
        store,
        item,
        status=status,
        error=error,
        completed_at=datetime.now(UTC).isoformat(),
    )


def _record(store: JobStatusStore, item: JobQueueItem, **changes) -> JobQueueItem:
    """Apply changes to a job's record, save it to the status store and return it."""
    updated = item.model_copy(update=changes)
    store.save(updated)
    return updated


def next_message(
    redis_client: redis.Redis,
    queue_name: str,
    retry_delay_seconds: float = RETRY_DELAY_SECONDS,
) -> Optional[str | bytes]:
    """Wait a short while for the next job on the queue.

    Returns the queue message, or None when none arrived in QUEUE_WAIT_SECONDS
    or Redis did not answer - the caller just asks again. A Redis that is slow
    or restarting is logged and waited out, so it never ends the worker.
    """
    try:
        popped = redis_client.blpop(queue_name, timeout=QUEUE_WAIT_SECONDS)
    except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError) as e:
        logger.warning("Redis did not answer (%s); trying again", type(e).__name__)
        time.sleep(retry_delay_seconds)
        return None
    if not popped:
        return None
    _, message = popped
    return message


def main():
    setup_logging()
    settings = Settings()

    redis_client = redis.Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        db=settings.redis_database,
        password=settings.redis_password.get_secret_value() if settings.redis_password else None,
        socket_timeout=SOCKET_TIMEOUT_SECONDS,
    )
    store = JobStatusStore(redis_client, ttl_seconds=settings.job_status_ttl_seconds)
    queue_name = settings.job_queue

    logger.info(f"Listening for jobs on Redis queue: {queue_name}")

    while True:
        # Payload expected to be a JSON string with job details
        message = next_message(redis_client, queue_name)
        if message is not None:
            handle_message(message, store, settings)


if __name__ == "__main__":
    main()
