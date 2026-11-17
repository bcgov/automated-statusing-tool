"""Tests for the job status store shared by the API and the engine worker."""

import pytest

from ast_api.tests.fakes import FakeRedis
from shared_models.job_store import JobStatusStore, job_key
from shared_models.models import JobQueueItem, JobStatus

pytestmark = pytest.mark.unit


def _item(**overrides) -> JobQueueItem:
    values = {
        "job_id": "job-1",
        "name": "Alice",
        "email": "alice@example.com",
        "region": "Cariboo",
        "source": "2",
        "aoi": {"type": "FeatureCollection", "features": []},
    }
    values.update(overrides)
    return JobQueueItem(**values)


def test_get_returns_none_for_unknown_job():
    assert JobStatusStore(FakeRedis()).get("missing") is None


def test_save_then_get_round_trips_the_record():
    store = JobStatusStore(FakeRedis())

    store.save(_item())
    loaded = store.get("job-1")

    assert loaded.name == "Alice"
    assert loaded.status == JobStatus.QUEUED


def test_status_record_leaves_out_the_aoi():
    """The shape is on the queue message only - the status record stays small."""
    client = FakeRedis()
    store = JobStatusStore(client)

    store.save(_item())

    assert '"aoi"' not in client.get(job_key("job-1"))
    assert store.get("job-1").aoi is None


def test_save_overwrites_the_previous_record():
    store = JobStatusStore(FakeRedis())
    store.save(_item())

    store.save(_item(status=JobStatus.FAILED, error="AOI too large"))

    assert store.get("job-1").status == JobStatus.FAILED
    assert store.get("job-1").error == "AOI too large"


def test_get_reads_a_record_returned_as_bytes():
    """The worker's Redis client does not decode responses, so it gets bytes."""
    client = FakeRedis()
    JobStatusStore(client).save(_item())
    client._values = {key: value.encode("utf-8") for key, value in client._values.items()}

    assert JobStatusStore(client).get("job-1").name == "Alice"
