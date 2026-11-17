import io
import json
import sqlite3
import zipfile
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

import ast_api.database as database
import ast_api.main as api_main
from ast_api.tests.fakes import FakeRedis
from ast_engine.storage import (
    JobStorageContext,
    MANIFEST_KEY,
    RAW_RESULTS_KEY,
    REPORT_CONTENT_TYPE,
    REPORT_KEY,
    create_results_writer,
    map_key,
)
from shared_models.job_store import JobStatusStore
from shared_models.models import JobStatus

pytestmark = pytest.mark.unit

# The engine's sample AOI, in every format an AOI can be uploaded in.
SAMPLE_AOI_DIR = Path(__file__).parents[2] / "ast_engine" / "tests" / "data" / "Test_Shape_A"

# A small square as an uploaded GeoJSON file.
AOI_GEOJSON = json.dumps({
    "type": "FeatureCollection",
    "features": [{
        "type": "Feature",
        "properties": {"owner": "not sent on"},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[-123.0, 49.0], [-123.0, 49.1], [-122.9, 49.1], [-122.9, 49.0], [-123.0, 49.0]]],
        },
    }],
}).encode("utf-8")

UPLOAD_FORM = {
    "name": "Alice",
    "email": "alice@example.com",
    "region": "Cariboo",
    "source": "2",
    "generate_maps": "false",
    "export_overlap_results": "true",
}


def _queued_items() -> list[dict]:
    """Everything on the job queue, oldest first."""
    queue = api_main.settings.job_queue
    return [json.loads(item) for item in api_main.redis_client.lrange(queue, 0, -1)]


def _post_upload(client, filename: str, content: bytes):
    return client.post(
        "/api/jobs",
        data=UPLOAD_FORM,
        files={"upload_file": (filename, content, "application/octet-stream")},
    )


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

    queue_items = _queued_items()
    assert len(queue_items) == 1
    assert queue_items[0]["name"] == "Alice"
    assert queue_items[0]["job_id"] == body["item"]["job_id"]
    # The worker looks the TANTALIS parcel up itself, so it is sent the identifiers.
    assert queue_items[0]["crown_file_number"] == "CF-1001"
    assert queue_items[0]["disposition_number"] == "DISP-2002"
    assert queue_items[0]["parcel_number"] == "PARCEL-3003"
    assert queue_items[0]["aoi"] is None
    assert queue_items[0]["created_at"]
    assert database.get_jobs() == [(
        1,
        "Alice",
        "alice@example.com",
        "Cariboo",
        "1",
        "CF-1001",
        "DISP-2002",
        "PARCEL-3003",
        1,
        0,
        JobStatus.QUEUED.value,
        body["item"]["job_id"],
    )]


def test_job_id_is_a_uuid(client, sample_job_payload):
    """The engine publishes results under the job id, and it identifies a job
    by UUID - so the API hands one out rather than the table's row number."""
    response = client.post("/api/jobs", data=sample_job_payload)

    UUID(response.json()["item"]["job_id"])


def test_jobs_table_does_not_include_area_of_interest(temp_db):
    with sqlite3.connect(temp_db) as connection:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(jobs)")
        }

    assert "area_of_interest" not in columns


def test_create_table_adds_source_to_existing_jobs_table(temp_db):
    with sqlite3.connect(temp_db) as connection:
        connection.execute("ALTER TABLE jobs DROP COLUMN source")

    database.create_table()

    with sqlite3.connect(temp_db) as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(jobs)")
        }

    assert "source" in columns


@pytest.mark.parametrize(
    "missing_identifier",
    ["crown_file_number", "disposition_number", "parcel_number"],
)
def test_tantalis_source_requires_all_identifiers(
    client,
    sample_job_payload,
    missing_identifier,
):
    payload = {**sample_job_payload, missing_identifier: ""}

    response = client.post("/api/jobs", data=payload)

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "TANTALIS source requires file, disposition, and parcel identifiers"
    )
    assert database.get_jobs() == []
    assert _queued_items() == []


def test_invalid_source_is_rejected_without_creating_job(
    client,
    sample_job_payload,
):
    payload = {**sample_job_payload, "source": "3"}

    response = client.post("/api/jobs", data=payload)

    assert response.status_code == 422
    assert database.get_jobs() == []
    assert _queued_items() == []


def test_get_job_by_id_returns_queue_item(client, sample_job_payload):
    create_response = client.post("/api/jobs", data=sample_job_payload)
    job_id = create_response.json()["item"]["job_id"]

    response = client.get(f"/api/jobs/{job_id}")

    assert response.status_code == 200
    assert response.json()["job_id"] == job_id
    assert response.json()["name"] == "Alice"


def test_get_job_by_id_still_answers_after_the_worker_takes_the_job(client, sample_job_payload):
    """A job leaves the queue when the worker picks it up; its status must not
    go with it."""
    job_id = client.post("/api/jobs", data=sample_job_payload).json()["item"]["job_id"]
    api_main.redis_client.lpop(api_main.settings.job_queue)

    response = client.get(f"/api/jobs/{job_id}")

    assert response.status_code == 200
    assert response.json()["status"] == JobStatus.QUEUED.value


def test_get_job_by_id_reports_what_the_worker_recorded(client, sample_job_payload):
    job_id = client.post("/api/jobs", data=sample_job_payload).json()["item"]["job_id"]
    store = JobStatusStore(api_main.redis_client)
    store.save(store.get(job_id).model_copy(update={"status": JobStatus.FAILED, "error": "AOI too large"}))

    body = client.get(f"/api/jobs/{job_id}").json()

    assert body["status"] == JobStatus.FAILED.value
    assert body["error"] == "AOI too large"


def test_get_job_by_id_returns_404_for_missing_job(client):
    response = client.get("/api/jobs/missing-job-id")

    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found"


def test_upload_source_reads_multipart_file(client):
    response = _post_upload(client, "aoi.geojson", AOI_GEOJSON)

    assert response.status_code == 201
    assert response.json()["upload"] == {
        "filename": "aoi.geojson",
        "size_bytes": len(AOI_GEOJSON),
    }
    assert database.get_jobs()[0][4] == "2"


def test_upload_source_queues_the_shape_for_the_worker(client):
    """The uploaded file is read into the AOI the worker runs: GeoJSON in
    longitude/latitude, geometry only."""
    _post_upload(client, "aoi.geojson", AOI_GEOJSON)

    aoi = _queued_items()[0]["aoi"]

    assert aoi["type"] == "FeatureCollection"
    assert len(aoi["features"]) == 1
    assert aoi["features"][0]["geometry"]["type"] == "Polygon"
    assert aoi["features"][0]["properties"] == {}


def test_job_responses_do_not_carry_the_shape(client):
    """The AOI is for the worker. It is left out of what the browser gets back."""
    created = _post_upload(client, "aoi.geojson", AOI_GEOJSON).json()
    job_id = created["item"]["job_id"]

    assert created["item"]["aoi"] is None
    assert client.get(f"/api/jobs/{job_id}").json()["aoi"] is None
    assert client.get("/api/jobs").json()[0]["aoi"] is None


@pytest.mark.parametrize(
    "filename",
    ["Test_Shape_A.geojson", "Test_Shape_A.kml", "Test_Shape_A.kmz", "Test_Shape_A.gpkg", "Test_Shape_A.zip"],
)
def test_upload_accepts_each_supported_format(client, filename):
    response = _post_upload(client, filename, (SAMPLE_AOI_DIR / filename).read_bytes())

    assert response.status_code == 201
    longitude, latitude = _first_coordinate(_queued_items()[0]["aoi"])
    assert -122 < longitude < -121 and 51 < latitude < 52


def test_upload_accepts_a_shapefile_zipped_without_its_folder(client):
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zipped:
        for part in (SAMPLE_AOI_DIR / "Test_Shape_A_shp").iterdir():
            zipped.write(part, part.name)

    response = _post_upload(client, "aoi.zip", archive.getvalue())

    assert response.status_code == 201


@pytest.mark.parametrize(
    "filename, content, expected_detail",
    [
        ("aoi.geojson", b'{"type":"FeatureCollection","features":[]}', "The file holds no shapes."),
        ("aoi.geojson", b"not a spatial file", "The file could not be read as a spatial file."),
        ("aoi.zip", b"not a zip file", "The file could not be read as a zip file."),
        ("aoi.shp", b"", "A shapefile must be uploaded as a .zip"),
        ("aoi.exe", b"", "Unsupported file type."),
        ("../../aoi", b"", "Unsupported file type."),
    ],
)
def test_upload_that_cannot_be_used_is_rejected_without_creating_job(
    client, filename, content, expected_detail
):
    response = _post_upload(client, filename, content)

    assert response.status_code == 422
    assert response.json()["detail"].startswith(expected_detail)
    assert database.get_jobs() == []
    assert _queued_items() == []


def test_upload_larger_than_the_limit_is_rejected(client, monkeypatch):
    monkeypatch.setattr(api_main.settings, "max_upload_bytes", 10)

    response = _post_upload(client, "aoi.geojson", AOI_GEOJSON)

    assert response.status_code == 413
    assert database.get_jobs() == []
    assert _queued_items() == []


def _first_coordinate(aoi: dict) -> tuple[float, float]:
    """The first longitude/latitude pair of an AOI's first shape."""
    coordinates = aoi["features"][0]["geometry"]["coordinates"]
    while isinstance(coordinates[0], list):
        coordinates = coordinates[0]
    return coordinates[0], coordinates[1]


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


def test_get_jobs_returns_empty_list_when_table_has_no_jobs(temp_db):
    assert database.get_jobs() == []


# --- Results ----------------------------------------------------------------
@pytest.fixture
def local_results(monkeypatch, tmp_path):
    """Results storage on local disk under tmp_path, as the worker would use."""
    monkeypatch.setenv("STORAGE_TYPE", "local")
    monkeypatch.setenv("RESULTS_LOCAL_ROOT", str(tmp_path / "results"))


def _set_status(job_id: str, **changes) -> None:
    """Rewrite a job's status record the way the worker does."""
    store = JobStatusStore(api_main.redis_client)
    store.save(store.get(job_id).model_copy(update=changes))


def test_results_returns_what_the_worker_published(client, sample_job_payload, local_results):
    item = client.post("/api/jobs", data=sample_job_payload).json()["item"]
    context = JobStorageContext(job_id=item["job_id"], created_date=item["created_at"][:10])
    create_results_writer(context).put_text(
        json.dumps({"job_id": item["job_id"], "results": []}),
        RAW_RESULTS_KEY,
        content_type="application/json",
    )
    _set_status(item["job_id"], status=JobStatus.COMPLETED)

    response = client.get(f"/api/jobs/{item['job_id']}/results")

    assert response.status_code == 200
    assert response.json() == {"job_id": item["job_id"], "results": []}


def test_results_returns_404_for_missing_job(client):
    response = client.get("/api/jobs/missing-job-id/results")

    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found"


def test_results_are_not_ready_until_the_job_completes(client, sample_job_payload):
    job_id = client.post("/api/jobs", data=sample_job_payload).json()["item"]["job_id"]

    response = client.get(f"/api/jobs/{job_id}/results")

    assert response.status_code == 409
    assert response.json()["detail"] == "Job has no results yet (status: Queued)"


def test_results_of_a_failed_job_say_why_it_failed(client, sample_job_payload):
    job_id = client.post("/api/jobs", data=sample_job_payload).json()["item"]["job_id"]
    _set_status(job_id, status=JobStatus.FAILED, error="AOI too large")

    response = client.get(f"/api/jobs/{job_id}/results")

    assert response.status_code == 409
    assert response.json()["detail"] == "Job failed: AOI too large"


def test_results_returns_404_when_nothing_was_published(client, sample_job_payload, local_results):
    job_id = client.post("/api/jobs", data=sample_job_payload).json()["item"]["job_id"]
    _set_status(job_id, status=JobStatus.COMPLETED)

    response = client.get(f"/api/jobs/{job_id}/results")

    assert response.status_code == 404
    assert response.json()["detail"] == "Results not found"


# --- Maps --------------------------------------------------------------------
def _publish_maps(item: dict, maps: dict[str, str]) -> None:
    """Publish a completed job's maps the way the worker does: one page per map
    and a manifest that lists them. maps is {name: title}."""
    context = JobStorageContext(job_id=item["job_id"], created_date=item["created_at"][:10])
    writer = create_results_writer(context)
    artifacts = {"raw_results": {"key": RAW_RESULTS_KEY, "content_type": "application/json"}}
    for name, title in maps.items():
        writer.put_text(f"<html><title>{title}</title></html>", map_key(name), content_type="text/html")
        artifacts[f"map_{name}"] = {
            "key": map_key(name),
            "content_type": "text/html",
            "metadata": {"title": title},
        }
    writer.put_text(json.dumps({"artifacts": artifacts}), MANIFEST_KEY, content_type="application/json")
    _set_status(item["job_id"], status=JobStatus.COMPLETED)


def test_maps_lists_the_published_maps_in_order(client, sample_job_payload, local_results):
    item = client.post("/api/jobs", data=sample_job_payload).json()["item"]
    _publish_maps(item, {"00overview": "Overview Map - All Overlaps", "provincial__Parks": "Parks"})

    response = client.get(f"/api/jobs/{item['job_id']}/maps")

    assert response.status_code == 200
    assert response.json() == [
        {"name": "00overview", "title": "Overview Map - All Overlaps"},
        {"name": "provincial__Parks", "title": "Parks"},
    ]


def test_maps_is_empty_for_a_job_published_without_maps(client, sample_job_payload, local_results):
    item = client.post("/api/jobs", data=sample_job_payload).json()["item"]
    _publish_maps(item, {})

    assert client.get(f"/api/jobs/{item['job_id']}/maps").json() == []


def test_map_returns_the_page(client, sample_job_payload, local_results):
    item = client.post("/api/jobs", data=sample_job_payload).json()["item"]
    _publish_maps(item, {"provincial__Parks": "Parks"})

    response = client.get(f"/api/jobs/{item['job_id']}/maps/provincial__Parks")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<title>Parks</title>" in response.text


def test_map_returns_404_for_a_map_the_job_does_not_have(client, sample_job_payload, local_results):
    item = client.post("/api/jobs", data=sample_job_payload).json()["item"]
    _publish_maps(item, {"provincial__Parks": "Parks"})

    response = client.get(f"/api/jobs/{item['job_id']}/maps/provincial__Wells")

    assert response.status_code == 404
    assert response.json()["detail"] == "Map not found"


@pytest.mark.parametrize("map_name", ["..", "../manifest", "a.b", "a/b", "", "name with space"])
def test_map_name_pattern_accepts_plain_names_only(map_name):
    assert api_main.MAP_NAME_PATTERN.fullmatch(map_name) is None
    assert api_main.MAP_NAME_PATTERN.fullmatch("provincial__Parks-2")


@pytest.mark.parametrize("map_name", ["a.b", "%2e%2e%2fmanifest", "name with space"])
def test_map_name_cannot_reach_outside_the_maps_folder(client, sample_job_payload, local_results, map_name):
    """The name becomes part of a storage key, so anything but a plain map name
    is refused before storage is touched."""
    item = client.post("/api/jobs", data=sample_job_payload).json()["item"]
    _publish_maps(item, {"provincial__Parks": "Parks"})

    response = client.get(f"/api/jobs/{item['job_id']}/maps/{map_name}")

    assert response.status_code == 404


@pytest.mark.parametrize("route", ["maps", "maps/provincial__Parks"])
def test_maps_are_not_ready_until_the_job_completes(client, sample_job_payload, route):
    job_id = client.post("/api/jobs", data=sample_job_payload).json()["item"]["job_id"]

    response = client.get(f"/api/jobs/{job_id}/{route}")

    assert response.status_code == 409
    assert response.json()["detail"] == "Job has no results yet (status: Queued)"


@pytest.mark.parametrize("route", ["maps", "maps/provincial__Parks"])
def test_maps_return_404_for_missing_job(client, route):
    response = client.get(f"/api/jobs/missing-job-id/{route}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found"


# --- Status report -----------------------------------------------------------
def test_report_is_sent_as_a_download(client, sample_job_payload, local_results, tmp_path):
    item = client.post("/api/jobs", data=sample_job_payload).json()["item"]
    workbook = tmp_path / "status-report.xlsx"
    workbook.write_bytes(b"PK\x03\x04 not really a workbook")
    context = JobStorageContext(job_id=item["job_id"], created_date=item["created_at"][:10])
    create_results_writer(context).put_file(workbook, REPORT_KEY, content_type=REPORT_CONTENT_TYPE)
    _set_status(item["job_id"], status=JobStatus.COMPLETED)

    response = client.get(f"/api/jobs/{item['job_id']}/report")

    assert response.status_code == 200
    assert response.content == workbook.read_bytes()
    assert response.headers["content-type"] == REPORT_CONTENT_TYPE
    assert response.headers["content-disposition"] == (
        f'attachment; filename="status-report-{item["job_id"]}.xlsx"'
    )


def test_report_returns_404_when_none_was_published(client, sample_job_payload, local_results):
    job_id = client.post("/api/jobs", data=sample_job_payload).json()["item"]["job_id"]
    _set_status(job_id, status=JobStatus.COMPLETED)

    response = client.get(f"/api/jobs/{job_id}/report")

    assert response.status_code == 404
    assert response.json()["detail"] == "Report not found"


def test_report_is_not_ready_until_the_job_completes(client, sample_job_payload):
    job_id = client.post("/api/jobs", data=sample_job_payload).json()["item"]["job_id"]

    response = client.get(f"/api/jobs/{job_id}/report")

    assert response.status_code == 409
