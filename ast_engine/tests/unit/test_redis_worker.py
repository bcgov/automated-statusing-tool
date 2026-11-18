"""
Tests for the queue worker: one queue message in, one status record out.

handle_message is tested directly, so no Redis server is needed - the status
store is given a small in-memory client. The jobs run over the sample files in
tests/data, with settings that carry no BCGW login.
"""

import json
from uuid import uuid4

import geopandas as gpd
import pytest
import redis

from ast_engine.config.registry import enrichment, utils
from ast_engine.config.registry.models import BaseDataset
from ast_engine.config.settings import Settings
from ast_engine.core.results import AstResults
from ast_engine.entry import worker
from ast_engine.entry.redis_worker import (
    QUEUE_WAIT_SECONDS,
    SOCKET_TIMEOUT_SECONDS,
    handle_message,
    next_message,
)
from ast_engine.entry.worker import INTERNAL_ERROR_MESSAGE
from ast_engine.storage import (
    RAW_RESULTS_KEY,
    JobStorageContext,
    create_results_reader,
    created_date,
)
from shared_models.job_store import JobStatusStore
from shared_models.models import JobQueueItem, JobStatus

pytestmark = pytest.mark.unit


class MemoryRedis:
    """The two Redis commands the status store uses, kept in a dict."""

    def __init__(self):
        self.values = {}

    def set(self, key, value, ex=None):
        self.values[key] = value

    def get(self, key):
        return self.values.get(key)


@pytest.fixture
def store() -> JobStatusStore:
    return JobStatusStore(MemoryRedis())


@pytest.fixture
def settings(monkeypatch, tmp_path, test_data_dir) -> Settings:
    """Local storage and a registry folder under tmp_path, and no BCGW login.

    The registry folder holds a common registry of one sample shapefile, built
    the way the spreadsheet ingestion builds one.
    """
    registry_dir = tmp_path / "registries"
    registry_dir.mkdir()
    dataset = BaseDataset(
        name="Test polygons",
        datasource=str(test_data_dir / "Test_Overlay" / "polygons.shp"),
        operator={"type": "overlay"},
    )
    enriched = enrichment.Enrich(dataset)
    enriched.enrich()
    utils.dump_yaml(
        utils.RegistryBuilder([enriched.build()]).build(),
        registry_dir / "one_status_common_datasets.yaml",
    )

    monkeypatch.setenv("STORAGE_TYPE", "local")
    monkeypatch.setenv("RESULTS_LOCAL_ROOT", str(tmp_path / "results"))
    monkeypatch.setenv("TEMP_DIR", str(tmp_path / "work"))
    monkeypatch.setenv("REGISTRY_OUTPUT_PATH", str(registry_dir))
    for name in ("ORACLE_USER", "ORACLE_PASSWORD", "ORACLE_HOST", "ORACLE_DATABASE"):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=None)
    monkeypatch.setattr(worker, "settings", settings)
    return settings


@pytest.fixture
def aoi_geojson(test_data_dir) -> dict:
    """Test_Shape_A as the API sends an uploaded AOI: GeoJSON in EPSG:4326."""
    gdf = gpd.read_file(test_data_dir / "Test_Shape_A" / "Test_Shape_A.geojson")
    return json.loads(gdf[[gdf.geometry.name]].to_crs("EPSG:4326").to_json())


def _message(**overrides) -> str:
    values = {
        "job_id": str(uuid4()),
        "name": "Alice",
        "email": "alice@example.com",
        "region": "Cariboo",
        "source": "2",
        "created_at": "2026-03-31T18:00:00+00:00",
    }
    values.update(overrides)
    return JobQueueItem(**values).model_dump_json()


def test_a_queued_upload_job_is_run_published_and_marked_completed(store, settings, aoi_geojson):
    message = _message(aoi=aoi_geojson)

    record = handle_message(message, store, settings)

    assert record.status == JobStatus.COMPLETED
    assert record.error is None
    assert record.completed_at
    assert store.get(record.job_id).status == JobStatus.COMPLETED

    # The results are where the API will look for them: under the job's own id.
    context = JobStorageContext(job_id=record.job_id, created_date=created_date(record.created_at))
    results = AstResults.model_validate_json(create_results_reader(context).get_text(RAW_RESULTS_KEY))
    assert str(results.job_id) == record.job_id


def test_a_message_given_as_bytes_is_read(store, settings, aoi_geojson):
    """A Redis client without decode_responses hands the message over as bytes."""
    message = _message(aoi=aoi_geojson).encode("utf-8")

    assert handle_message(message, store, settings).status == JobStatus.COMPLETED


def test_a_message_that_is_not_a_job_is_skipped(store, settings):
    assert handle_message('{"not": "a job"}', store, settings) is None
    assert store.client.values == {}


def test_a_job_with_no_aoi_fails_with_a_reason_for_the_user(store, settings):
    record = handle_message(_message(aoi=None), store, settings)

    assert record.status == JobStatus.FAILED
    assert record.error == "The job has no area of interest to analyse."
    assert store.get(record.job_id).status == JobStatus.FAILED


def test_a_tantalis_job_fails_clearly_when_the_worker_has_no_bcgw_login(store, settings):
    message = _message(source="1", crown_file_number="1", disposition_number="2", parcel_number="3")

    record = handle_message(message, store, settings)

    assert record.status == JobStatus.FAILED
    assert "BCGW connection" in record.error


def test_an_internal_failure_does_not_leak_its_details(store, settings, aoi_geojson, monkeypatch):
    """A missing registry folder is a deployment problem; the user is told only
    that the job could not be run, and the path stays in the log."""
    monkeypatch.setattr(settings, "registry_output_path", "/no/such/registry/folder")

    record = handle_message(_message(aoi=aoi_geojson), store, settings)

    assert record.status == JobStatus.FAILED
    assert record.error == INTERNAL_ERROR_MESSAGE


class QueueClient:
    """A Redis client whose blpop gives back, or raises, what it was built with."""

    def __init__(self, outcome):
        self.outcome = outcome
        self.timeouts = []

    def blpop(self, queue_name, timeout=0):
        self.timeouts.append(timeout)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def test_next_message_is_the_message_popped_from_the_queue():
    client = QueueClient(("ast_job_queue", b'{"job": 1}'))

    assert next_message(client, "ast_job_queue") == b'{"job": 1}'


def test_next_message_waits_no_longer_than_the_socket_allows():
    """A wait with no end is cut off by the client's socket timeout, as an error."""
    client = QueueClient(None)

    assert next_message(client, "ast_job_queue") is None
    assert client.timeouts == [QUEUE_WAIT_SECONDS]
    assert 0 < QUEUE_WAIT_SECONDS < SOCKET_TIMEOUT_SECONDS


@pytest.mark.parametrize(
    "error",
    [
        redis.exceptions.TimeoutError("Timeout reading from socket"),
        redis.exceptions.ConnectionError("Connection refused"),
    ],
)
def test_next_message_outlives_a_redis_that_is_slow_or_away(error):
    """An idle or restarting Redis must not end the worker; it tries again."""
    client = QueueClient(error)

    assert next_message(client, "ast_job_queue", retry_delay_seconds=0) is None
