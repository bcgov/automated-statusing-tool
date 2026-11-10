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
        "name": "Alice",
        "email": "alice@example.com",
        "region": "Cariboo",
        "source": "1",
        "crown_file_number": "CF-1001",
        "disposition_number": "DISP-2002",
        "parcel_number": "PARCEL-3003",
        "generate_maps": True,
        "export_overlap_results": False,
    }


def test_create_job_in_queue_and_db(client, sample_job_payload):
    response = client.post("/api/jobs", data=sample_job_payload)

    assert response.status_code == 201
    body = response.json()
    assert body["job"]["name"] == "Alice"
    assert body["item"]["region"] == "Cariboo"
    assert body["item"]["source"] == "1"
    assert body["item"]["status"] == JobStatus.QUEUED.value

    queue_items = [json.loads(item) for item in api_main.redis_client.lrange("jobs_queue", 0, -1)]
    assert len(queue_items) == 1
    assert queue_items[0]["name"] == "Alice"
    assert queue_items[0]["job_id"] == body["item"]["job_id"]
    assert database.get_jobs()[0][:5] == (
        1,
        "Alice",
        "alice@example.com",
        "Cariboo",
        "1",
    )


def test_jobs_table_does_not_include_area_of_interest(temp_db):
    with sqlite3.connect(temp_db) as connection:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(jobs)")
        }

    assert "area_of_interest" not in columns


def test_create_table_migrates_existing_job_columns(temp_db):
    with sqlite3.connect(temp_db) as connection:
        connection.execute("ALTER TABLE jobs RENAME COLUMN export_overlap_results TO export_overap_results")
        connection.execute("ALTER TABLE jobs DROP COLUMN source")

    database.create_table()

    with sqlite3.connect(temp_db) as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(jobs)").fetchall()
        }

    assert "source" in columns
    assert "export_overlap_results" in columns
    assert "export_overap_results" not in columns


def test_get_job_by_id_returns_queue_item(client, sample_job_payload):
    create_response = client.post("/api/jobs", data=sample_job_payload)
    job_id = create_response.json()["item"]["job_id"]

    response = client.get(f"/api/jobs/{job_id}")

    assert response.status_code == 200
    assert response.json()["job_id"] == job_id
    assert response.json()["name"] == "Alice"


def test_get_job_by_id_returns_404_for_missing_job(client):
    response = client.get("/api/jobs/missing-job-id")

    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found"


def test_upload_source_reads_multipart_file(client):
    response = client.post(
        "/api/jobs",
        data={
            "name": "Alice",
            "email": "alice@example.com",
            "region": "Cariboo",
            "source": "2",
            "generate_maps": "false",
            "export_overlap_results": "true",
        },
        files={"upload_file": ("aoi.geojson", b'{"type":"FeatureCollection","features":[]}', "application/geo+json")},
    )

    assert response.status_code == 201
    assert response.json()["upload"] == {
        "filename": "aoi.geojson",
        "size_bytes": len(b'{"type":"FeatureCollection","features":[]}'),
    }
    assert database.get_jobs()[0][4] == "2"


def test_upload_source_requires_file(client):
    response = client.post(
        "/api/jobs",
        data={
            "name": "Alice",
            "email": "alice@example.com",
            "region": "Cariboo",
            "source": "2",
        },
    )

    assert response.status_code == 422
