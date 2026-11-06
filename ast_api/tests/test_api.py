import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

import ast_api.database as database
import ast_api.main as api_main
from shared_models.models import CreateJob, JobStatus

pytestmark = pytest.mark.unit


class FakeRedis:
    def __init__(self):
        self._items = []

    def rpush(self, key, value):
        self._items.append(value)

    def lrange(self, key, start, end):
        stop = None if end == -1 else end + 1
        return self._items[start:stop]


@pytest.fixture
def temp_db(monkeypatch, tmp_path):
    db_path = tmp_path / "jobs.db"
    monkeypatch.setattr(database, "create_connection", lambda: sqlite3.connect(db_path))
    monkeypatch.setattr(api_main, "redis_client", FakeRedis())
    database.create_table()
    return db_path


@pytest.fixture
def client(temp_db):
    with TestClient(api_main.app) as test_client:
        yield test_client


@pytest.fixture
def sample_job_payload():
    return {
        "user": "alice",
        "date": "2026-09-23",
        "region": "Cariboo",
        "area_of_interest": "Northern Area",
        "crown_file_number": "CF-1001",
        "disposition_number": "DISP-2002",
        "parcel_number": "PARCEL-3003",
        "output_directory": "/tmp/output",
        "aoi_id": "AOI-42",
        "aoi_name": "Sample AOI",
        "aoi": {
            "type": "Feature",
            "properties": {"name": "Sample AOI"},
            "geometry": {"type": "Point", "coordinates": [0.0, 0.0]},
        },
    }


def test_create_job_in_queue_and_db(client, sample_job_payload):
    response = client.post("/api/jobs", json=sample_job_payload)

    assert response.status_code == 201
    body = response.json()
    assert body["job"]["user"] == "alice"
    assert body["item"]["region"] == "Cariboo"
    assert body["item"]["status"] == JobStatus.QUEUED.value

    queue_items = [json.loads(item) for item in api_main.redis_client.lrange("jobs_queue", 0, -1)]
    assert len(queue_items) == 1
    assert queue_items[0]["user"] == "alice"
    assert queue_items[0]["job_id"] == body["item"]["job_id"]


def test_get_job_by_id_returns_queue_item(client, sample_job_payload):
    create_response = client.post("/api/jobs", json=sample_job_payload)
    job_id = create_response.json()["item"]["job_id"]

    response = client.get(f"/api/jobs/{job_id}")

    assert response.status_code == 200
    assert response.json()["job_id"] == job_id
    assert response.json()["aoi_name"] == "Sample AOI"


def test_get_job_by_id_returns_404_for_missing_job(client):
    response = client.get("/api/jobs/missing-job-id")

    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found"


def _feature(properties):
    return {"type": "Feature", "properties": properties, "geometry": {"type": "Point", "coordinates": [0.0, 0.0]}}


def test_create_job_without_aoi_options_stores_and_queues_the_defaults(client, sample_job_payload, temp_db):
    response = client.post("/api/jobs", json=sample_job_payload)

    defaults = {"dissolve_mode": "full_union", "dissolve_fields": [], "allow_overlaps": False, "part_policy": "multi_part"}
    assert response.status_code == 201
    assert response.json()["item"]["aoi_options"] == defaults
    connection = sqlite3.connect(temp_db)
    stored = connection.execute("SELECT aoi_options FROM jobs").fetchone()[0]
    connection.close()
    assert json.loads(stored) == defaults


def test_create_job_sends_the_aoi_options_to_the_queue(client, sample_job_payload):
    sample_job_payload["aoi"] = {"type": "FeatureCollection", "features": [_feature({"BLOCK": "A"}), _feature({"BLOCK": "B"})]}
    sample_job_payload["aoi_options"] = {"dissolve_mode": "by_fields", "dissolve_fields": ["BLOCK"]}

    response = client.post("/api/jobs", json=sample_job_payload)

    assert response.status_code == 201
    queued = json.loads(api_main.redis_client.lrange("jobs_queue", 0, -1)[0])
    assert queued["aoi_options"]["dissolve_mode"] == "by_fields"
    assert queued["aoi_options"]["dissolve_fields"] == ["BLOCK"]


@pytest.mark.parametrize(
    "aoi_options, reason",
    [
        ({"dissolve_mode": "by_fields"}, "needs at least one dissolve field"),
        ({"dissolve_mode": "by_fields", "dissolve_fields": ["ZONE"]}, "not found in the AOI: ZONE"),
        ({"part_policy": "exploded"}, "not available yet"),
    ],
)
def test_create_job_refuses_bad_aoi_options_before_queueing(client, sample_job_payload, aoi_options, reason):
    sample_job_payload["aoi"] = {"type": "FeatureCollection", "features": [_feature({"BLOCK": "A"})]}
    sample_job_payload["aoi_options"] = aoi_options

    response = client.post("/api/jobs", json=sample_job_payload)

    assert response.status_code == 422
    assert reason in response.text
    assert api_main.redis_client.lrange("jobs_queue", 0, -1) == []


def test_create_table_adds_aoi_options_to_an_existing_jobs_db(temp_db, sample_job_payload):
    # A jobs.db made before #219 has no aoi_options column.
    connection = sqlite3.connect(temp_db)
    connection.execute("ALTER TABLE jobs DROP COLUMN aoi_options")
    connection.commit()
    connection.close()

    database.create_table()

    assert database.create_job(CreateJob(**sample_job_payload)) == 1
