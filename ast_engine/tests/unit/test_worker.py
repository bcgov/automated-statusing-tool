"""
Tests for the worker: one job in, the same job back with its outcome on it.

The jobs here run over the sample files in tests/data, so no database is needed.
The worker's settings are replaced with ones that carry no BCGW login, so these
tests never open a real connection whatever is in the developer's own .env.
"""

import io
import json
from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

import geopandas as gpd
import openpyxl
import pytest
from pydantic import SecretStr

from ast_engine.config.registry import enrichment, utils
from ast_engine.config.registry.models import BaseDataset, DataAdapter, Registry
from ast_engine.config.settings import Settings
from ast_engine.core.results import AstResults
from ast_engine.entry import worker
from ast_engine.entry.worker import AstJob, JobStatus, run_worker
from ast_engine.storage import (
    MANIFEST_KEY,
    RAW_RESULTS_KEY,
    REPORT_KEY,
    JobStorageContext,
    create_results_reader,
    created_date,
    map_key,
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


def _job(registry: Registry, aoi: dict, **options) -> AstJob:
    return AstJob(
        job_id=uuid4(),
        registries=[("demo", registry)],
        created_at=datetime.now(UTC).isoformat(),
        user="tester",
        aoi_id="aoi-1",
        aoi_name="Test AOI",
        aoi=aoi,
        status=JobStatus.QUEUED,
        **options,
    )


def _published(job: AstJob):
    """A reader over what the job published, and its manifest's artifact names."""
    context = JobStorageContext(job_id=job.job_id, created_date=created_date(job.created_at))
    reader = create_results_reader(context)
    manifest = json.loads(reader.get_text(MANIFEST_KEY))
    return reader, sorted(manifest["artifacts"])


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


# --- Maps and exported overlap results ---------------------------------------
def test_a_job_that_asks_for_maps_publishes_them(worker_settings, file_registry, aoi_geojson):
    job = run_worker(_job(file_registry, aoi_geojson, generate_maps=True), publish=True)

    assert job.status == JobStatus.COMPLETED
    reader, artifacts = _published(job)
    assert "map_00overview" in artifacts
    assert "map_demo__Test_polygons" in artifacts
    assert "<title>Test polygons</title>" in reader.get_text(map_key("demo__Test_polygons"))


def test_maps_alone_do_not_publish_the_saved_features(worker_settings, file_registry, aoi_geojson):
    """The features are saved to draw the maps from. They are only published
    when the job asked to export its overlap results."""
    job = run_worker(_job(file_registry, aoi_geojson, generate_maps=True), publish=True)

    _, artifacts = _published(job)
    assert [name for name in artifacts if name.startswith("gpkg_")] == []


def test_a_job_that_asks_to_export_overlap_results_publishes_the_features(
    worker_settings, file_registry, aoi_geojson
):
    job = run_worker(_job(file_registry, aoi_geojson, export_overlap_results=True), publish=True)

    _, artifacts = _published(job)
    assert [name for name in artifacts if name.startswith("gpkg_")] != []
    assert [name for name in artifacts if name.startswith("map_")] == []


def test_a_job_that_asks_for_neither_publishes_the_results_and_the_report(
    worker_settings, file_registry, aoi_geojson
):
    job = run_worker(_job(file_registry, aoi_geojson), publish=True)

    _, artifacts = _published(job)
    assert artifacts == ["raw_results", "report"]


def test_a_job_still_completes_when_its_maps_cannot_be_made(
    monkeypatch, worker_settings, file_registry, aoi_geojson
):
    """Maps are an extra. Failing to draw them must not cost the job its results."""
    def broken(**_):
        raise RuntimeError("no maps today")

    monkeypatch.setattr(worker, "generate_html_maps", broken)

    job = run_worker(_job(file_registry, aoi_geojson, generate_maps=True), publish=True)

    assert job.status == JobStatus.COMPLETED
    _, artifacts = _published(job)
    assert artifacts == ["raw_results", "report"]


# --- The status report -------------------------------------------------------
def _report(job: AstJob) -> openpyxl.Workbook:
    """The status report the job published, opened as a workbook."""
    reader, _ = _published(job)
    return openpyxl.load_workbook(io.BytesIO(reader.get_bytes(REPORT_KEY)))


def _cells(sheet) -> dict[str, str]:
    """Every filled cell of a sheet, as {coordinate: value}."""
    return {cell.coordinate: cell.value for row in sheet.iter_rows() for cell in row if cell.value is not None}


def test_a_published_job_has_a_status_report(worker_settings, file_registry, aoi_geojson):
    job = run_worker(
        _job(file_registry, aoi_geojson, region="Cariboo", crown_file_number="7410123"),
        publish=True,
    )

    book = _report(job)
    assert book.sheetnames == [
        "Crown Land Status",
        "Status of Conflict",
        "Conflicts & Constraints",
        "Data Sources",
    ]
    values = list(_cells(book["Conflicts & Constraints"]).values())
    assert "Cariboo" in values and "7410123" in values
    # The dataset is listed under its registry, having no category of its own.
    assert "demo" in values and "Test polygons" in values
    assert "demo" in _cells(book["Data Sources"]).values()


def test_the_report_links_to_the_maps_the_job_made(worker_settings, file_registry, aoi_geojson):
    job = run_worker(_job(file_registry, aoi_geojson, generate_maps=True), publish=True)

    sheet = _report(job)["Conflicts & Constraints"]
    links = {cell.value: cell.hyperlink.target for row in sheet.iter_rows() for cell in row if cell.hyperlink}

    assert links == {
        "Overview Map": "maps/00overview.html",
        "View Map": "maps/demo__Test_polygons.html",
    }


def test_the_report_links_through_the_api_when_its_address_is_known(
    monkeypatch, worker_settings, file_registry, aoi_geojson
):
    """A relative link only works beside the maps folder. With the API's public
    address configured the links work from a downloaded report."""
    monkeypatch.setattr(worker_settings, "api_public_url", "https://ast.example.gov.bc.ca/")

    job = run_worker(_job(file_registry, aoi_geojson, generate_maps=True), publish=True)

    sheet = _report(job)["Conflicts & Constraints"]
    links = {cell.value: cell.hyperlink.target for row in sheet.iter_rows() for cell in row if cell.hyperlink}
    assert links["View Map"] == f"https://ast.example.gov.bc.ca/api/jobs/{job.job_id}/maps/demo__Test_polygons"


def test_the_tab1_registry_is_left_off_the_conflicts_tab(worker_settings, file_registry, aoi_geojson):
    """Its datasets fill the Crown Land Status tab instead."""
    job = run_worker(_job(file_registry, aoi_geojson, tab1_registry="demo"), publish=True)

    assert "Test polygons" not in _cells(_report(job)["Conflicts & Constraints"]).values()


def test_without_a_bcgw_connection_the_report_says_what_was_not_checked(
    worker_settings, file_registry, aoi_geojson
):
    """A worker with no BCGW login cannot read the inactive tenures, and this
    job ran no Tab 1 registry. The report says so; it does not look clear."""
    job = run_worker(_job(file_registry, aoi_geojson), publish=True)

    book = _report(job)
    conflict = list(_cells(book["Status of Conflict"]).values())
    assert any(text.startswith("ERROR: The AST was unable to evaluate") for text in conflict)
    status = _cells(book["Crown Land Status"])
    assert "Not checked" in status.values()


def test_the_report_carries_the_tantalis_facts_of_the_file(
    monkeypatch, worker_settings, file_registry, aoi_geojson
):
    """With a connection, the applicant, the tenure and the inactive tenures on
    the AOI are read from TANTALIS and written into the report."""
    monkeypatch.setattr(worker, "fetch_applicant_name", lambda cursor, disposition: "ACME GRAVEL LTD.")
    monkeypatch.setattr(worker, "fetch_received_dates", lambda cursor, disposition: ["2026-01-15"])
    monkeypatch.setattr(
        worker,
        "fetch_tenure_details",
        lambda cursor, file, disposition, parcel: {"TENURE_TYPE": ["LICENCE"], "TENURE_AREA_IN_HECTARES": ["12.5"]},
    )
    monkeypatch.setattr(
        worker,
        "fetch_inactive_tenures",
        lambda connection, cursor, aoi: [
            worker.InactiveTenure(disposition_id=900, file_number="7400001",
                                  interest_type="QUARRYING LICENCE", holders="Old Holder Ltd."),
        ],
    )
    job = _job(
        file_registry, aoi_geojson,
        crown_file_number="7410123", disposition_number="55", parcel_number="987654",
    )

    job = run_worker(job, publish=True, oracle_connection=MagicMock())

    book = _report(job)
    status = list(_cells(book["Crown Land Status"]).values())
    assert "ACME GRAVEL LTD." in status
    assert "12.5 hectares" in status
    assert "LICENCE" in status and "2026-01-15" in status
    conflict = list(_cells(book["Status of Conflict"]).values())
    assert "Disp Trans SID: 900 FILE NUMBER: 7400001" in conflict
    assert "Old Holder Ltd." in conflict


def test_a_failed_tantalis_lookup_does_not_cost_the_job_its_report(
    monkeypatch, worker_settings, file_registry, aoi_geojson
):
    def broken(*_, **__):
        raise RuntimeError("BCGW went away")

    monkeypatch.setattr(worker, "fetch_applicant_name", broken)
    monkeypatch.setattr(worker, "fetch_inactive_tenures", broken)
    job = _job(file_registry, aoi_geojson, crown_file_number="7410123", disposition_number="55")

    job = run_worker(job, publish=True, oracle_connection=MagicMock())

    assert job.status == JobStatus.COMPLETED
    conflict = list(_cells(_report(job)["Status of Conflict"]).values())
    assert any(text.startswith("ERROR: The AST was unable to evaluate") for text in conflict)


def test_a_job_still_completes_when_its_report_cannot_be_written(
    monkeypatch, worker_settings, file_registry, aoi_geojson
):
    def broken(*_, **__):
        raise RuntimeError("no report today")

    monkeypatch.setattr(worker, "write_status_report", broken)

    job = run_worker(_job(file_registry, aoi_geojson), publish=True)

    assert job.status == JobStatus.COMPLETED
    _, artifacts = _published(job)
    assert artifacts == ["raw_results"]


def test_a_job_with_tab3_suppressed_reports_the_first_two_tabs_and_makes_no_maps(
    worker_settings, file_registry, aoi_geojson
):
    """The maps belong to Tab 3: they show what its datasets found."""
    job = run_worker(
        _job(file_registry, aoi_geojson, tab1_registry="demo", suppress_tab3=True, generate_maps=True),
        publish=True,
    )

    assert job.status == JobStatus.COMPLETED
    assert _report(job).sheetnames == ["Crown Land Status", "Status of Conflict"]
    _, artifacts = _published(job)
    assert not [name for name in artifacts if name.startswith("map_")]


# --- a BCGW that is set up but cannot be reached ------------------------------


@pytest.fixture
def bcgw_unreachable(monkeypatch, worker_settings) -> Settings:
    """Worker settings that name a BCGW login, with a database that refuses it."""
    settings = worker_settings.model_copy(update={
        "oracle_user": "someone",
        "oracle_password": SecretStr("not-a-real-password"),
        "oracle_host": "bcgw.example",
        "oracle_database": "db.example",
    })
    monkeypatch.setattr(worker, "settings", settings)

    def refuse(**login):
        raise ConnectionError("Oracle connection failed for bcgw.example:1521/db.example: ORA-12170")

    monkeypatch.setattr(worker, "OracleConnection", refuse)
    return settings


@pytest.fixture
def bcgw_registry(file_registry) -> Registry:
    """A registry of one dataset that is read from BCGW."""
    dataset = file_registry.datasets[0].model_copy(update={
        "name": "Parks",
        "datasource": "WHSE_TANTALIS.TA_PARK_ECORES_PA_SVW",
        "data_adapter": DataAdapter.ORACLE,
    })
    return file_registry.model_copy(update={"datasets": [dataset]})


def test_a_bcgw_that_cannot_be_reached_is_run_without(bcgw_unreachable, caplog):
    """The same as a worker with no BCGW login: what needs BCGW says so, and
    what does not is still run."""
    assert worker.open_oracle_connection(bcgw_unreachable) is None
    assert "BCGW could not be reached" in caplog.text
    assert "not-a-real-password" not in caplog.text


def test_a_job_that_needs_no_bcgw_still_runs_when_bcgw_cannot_be_reached(
    bcgw_unreachable, file_registry, aoi_geojson
):
    job = run_worker(_job(file_registry, aoi_geojson), publish=True)

    assert job.status == JobStatus.COMPLETED
    assert job.error is None


@pytest.mark.parametrize("settings_fixture", ["worker_settings", "bcgw_unreachable"])
def test_a_job_that_needs_bcgw_fails_saying_so_when_there_is_no_connection(
    settings_fixture, request, bcgw_registry, aoi_geojson
):
    """Not the catch-all "could not be run": the user can act on this one, by
    trying again later. And not a report with every dataset marked failed."""
    request.getfixturevalue(settings_fixture)

    job = run_worker(_job(bcgw_registry, aoi_geojson), publish=True)

    assert job.status == JobStatus.FAILED
    assert job.error == worker.BCGW_UNAVAILABLE_MESSAGE
    assert job.error != worker.INTERNAL_ERROR_MESSAGE
