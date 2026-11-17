"""Tests for turning a queue message into a job the worker can run."""

from unittest.mock import MagicMock
from uuid import uuid4

import geopandas as gpd
import pytest
from shapely.geometry import box

from ast_engine.config.registry import utils
from ast_engine.core.data_adapters.exceptions import DataReadError
from ast_engine.entry import job_builder
from ast_engine.entry.job_builder import (
    JobRequestError,
    build_ast_job,
    load_registries,
    normalize_region,
    resolve_aoi,
)
from shared_models.models import JobQueueItem

pytestmark = pytest.mark.unit

AOI = {
    "type": "FeatureCollection",
    "features": [{
        "type": "Feature",
        "properties": {},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[-123.0, 49.0], [-123.0, 49.1], [-122.9, 49.1], [-122.9, 49.0], [-123.0, 49.0]]],
        },
    }],
}


def _item(**overrides) -> JobQueueItem:
    values = {
        "job_id": str(uuid4()),
        "name": "Alice",
        "email": "alice@example.com",
        "region": "Kootenay Boundary",
        "source": "2",
        "aoi": AOI,
        "created_at": "2026-03-31T18:00:00+00:00",
    }
    values.update(overrides)
    return JobQueueItem(**values)


def _write_registry(folder, name: str) -> None:
    """Write an empty registry yaml under one of the names the worker looks for."""
    utils.dump_yaml(utils.RegistryBuilder([]).build(), folder / f"{name}.yaml")


@pytest.mark.parametrize(
    "region, expected",
    [
        ("Cariboo", "cariboo"),
        ("Kootenay Boundary", "kootenay_boundary"),
        (" South Coast ", "south_coast"),
        ("thompson_okanagan", "thompson_okanagan"),
    ],
)
def test_normalize_region(region, expected):
    assert normalize_region(region) == expected


def test_load_registries_returns_common_then_region_then_tab1(tmp_path):
    for name in ("one_status_common_datasets", "one_status_kootenay_boundary_specific", "tab1"):
        _write_registry(tmp_path, name)

    names = [name for name, _ in load_registries("Kootenay Boundary", tmp_path)]

    assert names == ["one_status_common_datasets", "one_status_kootenay_boundary_specific", "tab1"]


def test_load_registries_runs_without_the_optional_registries(tmp_path):
    _write_registry(tmp_path, "one_status_common_datasets")

    names = [name for name, _ in load_registries("Cariboo", tmp_path)]

    assert names == ["one_status_common_datasets"]


def test_load_registries_requires_the_common_registry(tmp_path):
    _write_registry(tmp_path, "one_status_cariboo_specific")

    with pytest.raises(FileNotFoundError, match="common registry"):
        load_registries("Cariboo", tmp_path)


def test_load_registries_requires_a_configured_folder():
    with pytest.raises(FileNotFoundError, match="registry_output_path"):
        load_registries("Cariboo", None)


def test_resolve_aoi_returns_the_uploaded_shape():
    assert resolve_aoi(_item(), oracle_connection=None) == AOI


def test_resolve_aoi_rejects_an_upload_job_with_no_shape():
    with pytest.raises(JobRequestError):
        resolve_aoi(_item(aoi=None), oracle_connection=None)


def test_resolve_aoi_needs_a_connection_for_tantalis():
    item = _item(source="1", aoi=None, crown_file_number="1", disposition_number="2", parcel_number="3")

    with pytest.raises(JobRequestError, match="BCGW connection"):
        resolve_aoi(item, oracle_connection=None)


def test_resolve_aoi_looks_a_tantalis_parcel_up_and_returns_it_in_4326(monkeypatch):
    """The parcel comes back from BCGW in BC Albers; the job carries it as GeoJSON."""
    parcel = gpd.GeoDataFrame(geometry=[box(1_200_000, 460_000, 1_201_000, 461_000)], crs="EPSG:3005")
    lookup = MagicMock(return_value=parcel)
    monkeypatch.setattr(job_builder, "fetch_tantalis_aoi", lookup)
    connection = MagicMock()
    item = _item(source="1", aoi=None, crown_file_number="7410123", disposition_number="55", parcel_number="9")

    aoi = resolve_aoi(item, oracle_connection=connection)

    lookup.assert_called_once_with(connection.connection, connection.cursor, "7410123", "55", "9")
    longitude, latitude = aoi["features"][0]["geometry"]["coordinates"][0][0]
    assert -140 < longitude < -113 and 48 < latitude < 61


def test_resolve_aoi_reports_a_parcel_that_does_not_exist(monkeypatch):
    monkeypatch.setattr(
        job_builder,
        "fetch_tantalis_aoi",
        MagicMock(side_effect=DataReadError("No Tantalis parcel found")),
    )
    item = _item(source="1", aoi=None, crown_file_number="1", disposition_number="2", parcel_number="3")

    with pytest.raises(JobRequestError, match="No Tantalis parcel found"):
        resolve_aoi(item, oracle_connection=MagicMock())


def test_build_ast_job_keeps_the_job_id_and_timestamp(tmp_path):
    _write_registry(tmp_path, "one_status_common_datasets")
    item = _item()

    job = build_ast_job(item, registry_dir=tmp_path)

    assert str(job.job_id) == item.job_id
    assert job.created_at == item.created_at
    assert job.user == "Alice"
    assert job.aoi == AOI
