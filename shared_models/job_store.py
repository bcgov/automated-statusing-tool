"""
Job status store: where the API and the engine worker meet after a job is queued.

The job queue only carries a job one way, from the API to the worker, and a job
is gone from it the moment the worker picks it up. This store is what lets the
API still answer "how is my job doing?" afterwards: the API writes a record when
it accepts a job, the worker rewrites it as the job moves through Processing,
Publishing and Completed (or Failed), and the API reads it back for the browser.

Records are kept in Redis, one key per job (ast_job:<job_id>), as the JSON form
of a JobQueueItem. Redis is used because both sides already connect to it for
the queue - the API's own jobs table lives in a SQLite file the worker cannot
reach from its own container.
"""

from typing import Any, Optional

from .models import JobQueueItem

# Redis key prefix for one job's status record.
JOB_KEY_PREFIX = "ast_job"

# The area of interest is on the queue message, not in the status record.
_STATUS_EXCLUDE = {"aoi"}


def job_key(job_id: str) -> str:
    """The Redis key holding one job's status record."""
    return f"{JOB_KEY_PREFIX}:{job_id}"


class JobStatusStore:
    """Reads and writes job status records in Redis.

    client       a redis.Redis client (or anything with the same get / set).
                 It works with or without decode_responses, so the API and the
                 worker can each pass the client they already have.
    ttl_seconds  how long a record is kept, counted from its last update. A
                 record holds the submitter's name and email, so it should not
                 outlive its use; None keeps it until Redis is cleared.
    """

    def __init__(self, client: Any, ttl_seconds: Optional[int] = None):
        self.client = client
        self.ttl_seconds = ttl_seconds

    def save(self, item: JobQueueItem) -> None:
        """Write (or overwrite) one job's status record."""
        payload = item.model_dump_json(exclude=_STATUS_EXCLUDE)
        self.client.set(job_key(item.job_id), payload, ex=self.ttl_seconds)

    def get(self, job_id: str) -> Optional[JobQueueItem]:
        """Return one job's status record, or None when there is none."""
        payload = self.client.get(job_key(job_id))
        if payload is None:
            return None
        return JobQueueItem.model_validate_json(payload)
