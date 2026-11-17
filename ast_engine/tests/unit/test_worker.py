"""
Tests for the worker: one job in, the same job back with its outcome on it.

The jobs here run over the sample files in tests/data, so no database is needed.
The worker's settings are replaced with ones that carry no BCGW login, so these
tests never open a real connection whatever is in the developer's own .env.
"""

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

import geopandas as gpd
import pytest

from ast_engine.config.registry import enrichment, utils
from ast_engine.config.registry.models import BaseDataset, Registry
from ast_engine.config.settings import Settings
from ast_engine.core.results import AstResults
from ast_engine.entry import worker
from ast_engine.entry.worker import AstJob, JobStatus, run_worker
from ast_engine.storage import (
    RAW_RESULTS_KEY,
    JobStorageContext,
    create_results_reader,
    created_date,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def worker_settings(monkeypatch, tmp_path) -> Settings:
    """Worker settings with local storage under tmp_path and no BCGW login."""
    monkeypatch.setenv("STORAGE_TYPE", "local")
    monkeypatch.setenv("RESULTS_LOCAL_ROOT", str(tmp_path / "results"))
    monkeypatch.setenv("TEMP_DIR", str(tmp_path / "work"))
    for name in ("ORACLE_USER", "ORACLE_PASSWORD", "ORACLE_HOST", "ORACLE_DATABASE"):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=None)
    monkeypatch.setattr(worker, "settings", settings)
    return settings


@pytest.fixture
def file_registry(test_data_dir) -> Registry:
    """A one-dataset registry over a sample shapefile, built the way the
    spreadsheet ingestion builds one."""
    dataset = BaseDataset(
        name="Test polygons",
        datasource=str(test_data_dir / "Test_Overlay" / "polygons.shp"),
        operator={"type": "overlay"},
    )
    enriched = enrichment.Enrich(dataset)
    enriched.enrich()
    return utils.RegistryBuilder([enriched.build()]).build()


@pytest.fixture
def aoi_geojson(test_data_dir) -> dict:
    """Test_Shape_A as the worker receives an AOI: GeoJSON in EPSG:4326."""
    gdf = gpd.read_file(test_data_dir / "Test_Shape_A" / "Test_Shape_A.geojson")
    return json.loads(gdf[[gdf.geometry.name]].to_crs("EPSG:4326").to_json())


def _job(registry: Registry, aoi: dict) -> AstJob:
    return AstJob(
        job_id=uuid4(),
        registries=[("demo", registry)],
        created_at=datetime.now(UTC).isoformat(),
        user="tester",
        aoi_id="aoi-1",
        aoi_name="Test AOI",
        aoi=aoi,
        status=JobStatus.QUEUED,
    )


def test_run_worker_completes_a_file_job_without_a_bcgw_login(
    worker_settings, file_registry, aoi_geojson
):
    job = run_worker(_job(file_registry, aoi_geojson), publish=False)

    assert job.status == JobStatus.COMPLETED
    assert job.error is None


def test_run_worker_reports_a_failed_job_instead_of_returning_nothing(
    worker_settings, file_registry
):
    """An AOI with no features cannot be built; the job comes back marked
    Failed, with the reason, so the caller can report it."""
    empty_aoi = {"type": "FeatureCollection", "features": []}

    job = run_worker(_job(file_registry, empty_aoi), publish=False)

    assert job.status == JobStatus.FAILED
    assert job.error


def test_run_worker_publishes_results_where_the_reader_finds_them(
    worker_settings, file_registry, aoi_geojson
):
    job = run_worker(_job(file_registry, aoi_geojson), publish=True)

    assert job.status == JobStatus.COMPLETED
    context = JobStorageContext(job_id=job.job_id, created_date=created_date(job.created_at))
    results = AstResults.model_validate_json(
        create_results_reader(context).get_text(RAW_RESULTS_KEY)
    )
    assert results.job_id == job.job_id
    assert [group.status for group in results.results] == ["success"]


def test_published_results_are_filed_under_the_day_not_the_timestamp(
    worker_settings, file_registry, aoi_geojson, tmp_path
):
    """The storage path takes a YYYY-MM-DD date. A full timestamp holds colons,
    which a Windows path cannot carry."""
    job = run_worker(_job(file_registry, aoi_geojson), publish=True)

    date_folders = [path.name for path in (tmp_path / "results").rglob("date=*")]
    assert date_folders == [f"date={job.created_at[:10]}"]


def test_run_worker_leaves_a_connection_it_was_given_open(
    worker_settings, file_registry, aoi_geojson
):
    """The caller that opened the connection owns it and closes it."""
    connection = MagicMock()

    job = run_worker(_job(file_registry, aoi_geojson), oracle_connection=connection)

    assert job.status == JobStatus.COMPLETED
    connection.close.assert_not_called()


def test_run_worker_closes_the_connection_it_opened(
    monkeypatch, worker_settings, file_registry, aoi_geojson
):
    opened = MagicMock()
    monkeypatch.setattr(worker, "open_oracle_connection", lambda settings: opened)

    run_worker(_job(file_registry, aoi_geojson))

    opened.close.assert_called_once()


def test_open_oracle_connection_is_skipped_without_a_login(worker_settings):
    assert worker.open_oracle_connection(worker_settings) is None
