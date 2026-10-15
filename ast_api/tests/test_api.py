import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

import ast_api.database as database
import ast_api.main as api_main
from shared_models.models import JobStatus

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
