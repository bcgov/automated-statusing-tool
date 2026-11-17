"""
End-to-end test of one job: submitted to the API, run by the worker, read back.

    uv run pytest ast_api/tests -m integration

This is the whole path a job takes in the running application, with the two
network pieces replaced: Redis is an in-memory fake that the API and the worker
share, and results storage is a folder on local disk. Everything between them is
the real code - the API route, the queue message, the worker, the engine run over
the sample datasets in ast_engine/tests/data, publishing, and the results route.
No database is needed.
"""

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import ast_api.database as database
import ast_api.main as api_main
from ast_api.tests.fakes import FakeRedis
from ast_engine.config.registry import enrichment, utils
from ast_engine.config.registry.models import BaseDataset
from ast_engine.config.settings import Settings
from ast_engine.entry import worker
from ast_engine.entry.redis_worker import handle_message
from shared_models.job_store import JobStatusStore
from shared_models.models import JobStatus

pytestmark = pytest.mark.integration

DATA_DIR = Path(__file__).parents[2] / "ast_engine" / "tests" / "data"
AOI_FILE = DATA_DIR / "Test_Shape_A" / "Test_Shape_A.kml"

# The sample datasets the job is run against, and what Test_Shape_A covers in
# them (the same figures test_file_pipeline.py checks the engine against).
PARCELS = DATA_DIR / "Test_Data_PMBC_PARCEL_FABRIC.gdb" / "WHSE_CADASTRE_PMBC_PARCEL_FABRIC_POLY_FA_SVW"
ROADS = DATA_DIR / "Test_Data_FOREST_TENURE_ROAD_shp" / "WHSE_FOREST_TENURE_FTEN_ROAD_SECTION_LINES_SVW.shp"
PARCELS_IN_AOI = 10
ROADS_WITHIN_100M = 7


@pytest.fixture
def redis_client(monkeypatch) -> FakeRedis:
    """One in-memory Redis, shared by the API and the worker."""
    client = FakeRedis()
    monkeypatch.setattr(api_main, "redis_client", client)
    return client


@pytest.fixture
def client(redis_client, monkeypatch, tmp_path):
    db_path = tmp_path / "jobs.db"
    monkeypatch.setattr(database, "create_connection", lambda: sqlite3.connect(db_path))
    with TestClient(api_main.app) as test_client:
        yield test_client


@pytest.fixture
def worker_settings(monkeypatch, tmp_path) -> Settings:
    """Worker settings for a file-only run: a registry folder holding the common
    registry, local results storage, and no BCGW login."""
    registry_dir = tmp_path / "registries"
    registry_dir.mkdir()
    datasets = []
    for dataset in (
        BaseDataset(name="Parcels", datasource=str(PARCELS), operator={"type": "overlay"}),
        BaseDataset(name="Roads", datasource=str(ROADS), operator={"type": "within_distance", "distance_m": 100}),
    ):
        enriched = enrichment.Enrich(dataset)
        enriched.enrich()
        datasets.append(enriched.build())
    utils.dump_yaml(
        utils.RegistryBuilder(datasets).build(),
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


def test_an_uploaded_job_runs_from_submission_to_results(client, redis_client, worker_settings):
    # 1. The browser submits the form with an uploaded AOI.
    submitted = client.post(
        "/api/jobs",
        data={"name": "Alice", "email": "alice@example.com", "region": "Cariboo", "source": "2"},
        files={"upload_file": (AOI_FILE.name, AOI_FILE.read_bytes(), "application/vnd.google-earth.kml+xml")},
    )
    assert submitted.status_code == 201
    job_id = submitted.json()["item"]["job_id"]
    assert client.get(f"/api/jobs/{job_id}").json()["status"] == JobStatus.QUEUED.value

    # 2. The worker takes the job off the queue and runs it.
    message = redis_client.lpop(api_main.settings.job_queue)
    record = handle_message(message, JobStatusStore(redis_client), worker_settings)
    assert record.status == JobStatus.COMPLETED, record.error

    # 3. The browser sees the job complete and reads its results.
    assert client.get(f"/api/jobs/{job_id}").json()["status"] == JobStatus.COMPLETED.value
    results = client.get(f"/api/jobs/{job_id}/results")
    assert results.status_code == 200

    body = results.json()
    assert body["job_id"] == job_id
    by_dataset = {group["dataset_name"]: group for group in body["results"]}
    assert set(by_dataset) == {"Parcels", "Roads"}
    assert all(group["status"] == "success" for group in by_dataset.values())
    assert by_dataset["Parcels"]["parts"][0]["result"]["feature_count"] == PARCELS_IN_AOI
    assert by_dataset["Roads"]["parts"][0]["result"]["feature_count"] == ROADS_WITHIN_100M


def test_a_job_that_asks_for_maps_gets_them(client, redis_client, worker_settings):
    """Generate Maps on the form carries through to pages the browser can open."""
    submitted = client.post(
        "/api/jobs",
        data={
            "name": "Alice",
            "email": "alice@example.com",
            "region": "Cariboo",
            "source": "2",
            "generate_maps": "true",
        },
        files={"upload_file": (AOI_FILE.name, AOI_FILE.read_bytes(), "application/vnd.google-earth.kml+xml")},
    )
    job_id = submitted.json()["item"]["job_id"]

    record = handle_message(
        redis_client.lpop(api_main.settings.job_queue),
        JobStatusStore(redis_client),
        worker_settings,
    )
    assert record.status == JobStatus.COMPLETED, record.error

    maps = client.get(f"/api/jobs/{job_id}/maps").json()
    assert [item["title"] for item in maps] == ["Overview Map - All Overlaps", "Parcels", "Roads"]

    for item in maps:
        page = client.get(f"/api/jobs/{job_id}/maps/{item['name']}")
        assert page.status_code == 200
        assert f"<title>{item['title']}</title>" in page.text


def test_a_job_the_worker_cannot_run_is_reported_to_the_browser(client, redis_client, worker_settings):
    """A TANTALIS job needs BCGW. With no login on the worker the job fails, and
    the browser is told why rather than left waiting."""
    submitted = client.post(
        "/api/jobs",
        data={
            "name": "Alice",
            "email": "alice@example.com",
            "region": "Cariboo",
            "source": "1",
            "crown_file_number": "7410123",
            "disposition_number": "55",
            "parcel_number": "9",
        },
    )
    job_id = submitted.json()["item"]["job_id"]

    handle_message(
        redis_client.lpop(api_main.settings.job_queue),
        JobStatusStore(redis_client),
        worker_settings,
    )

    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == JobStatus.FAILED.value
    assert "BCGW connection" in job["error"]
    assert client.get(f"/api/jobs/{job_id}/results").status_code == 409
