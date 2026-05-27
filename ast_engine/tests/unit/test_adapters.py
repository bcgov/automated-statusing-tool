#\tests\unit\test_adapters.py
"""
File-based adapter tests

Purpose:
- SpatialFilter validation (the contract every adapter takes)
- FileSpatialAdapter reads one test per supported format
- ReadOptions features: spatial_filter, keep_columns, definition_query


HOW TO EXTEND:
-------------
1. Add a new test function per format the adapter must handle
2. Add a new test function per ReadOptions feature
3. Keep test names short and readable
4. Reuse the Test_Shape_A data already in tests/data/

Example:
def test_file_adapter_read_shp()
def test_file_adapter_read_gpkg()
def test_file_adapter_read_kml()
def test_file_adapter_spatial_filter()
def test_file_adapter_keep_columns()
def test_file_adapter_definition_query()
"""
import pytest
from pathlib import Path
import geopandas as gpd

from ast_engine.core.data_adapters.file.adapter import FileSpatialAdapter
from ast_engine.core.data_adapters.base import ReadOptions, SpatialFilter


# Test data folder + one constant per supported format.
# adapter must read. shp / gpkg / geojson are EPSG:3005, kml is EPSG:4326.
DATA_DIR = Path(__file__).parents[1] / "data" / "Test_Shape_A"
SHP = DATA_DIR / "Test_Shape_A_shp" / "Test_Shape_A.shp"
GPKG = DATA_DIR / "Test_Shape_A.gpkg"
GEOJSON = DATA_DIR / "Test_Shape_A.geojson"
KML = DATA_DIR / "Test_Shape_A.kml"
KMZ = DATA_DIR / "Test_Shape_A.kmz"

# Tags every test in this file as "unit"
# replaces a per-function @pytest.mark.unit decorator on each test
pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# SpatialFilter validation
# (SpatialFilter rejects bad inputs at construction time, before any adapter
# is called. Tests live here because SpatialFilter is the adapter contract.)
# ---------------------------------------------------------------------------

def _valid_aoi() -> gpd.GeoDataFrame:
    """Re-read the test shapefile as a projected AOI for SpatialFilter cases."""
    return gpd.read_file(SHP)


def test_spatial_filter_empty_aoi_raises():
    empty = gpd.GeoDataFrame(geometry=[], crs="EPSG:3005")
    with pytest.raises(ValueError):
        SpatialFilter(aoi=empty)


def test_spatial_filter_unknown_predicate_raises():
    with pytest.raises(ValueError):
        SpatialFilter(aoi=_valid_aoi(), predicate="contains")


def test_spatial_filter_within_distance_requires_distance():
    with pytest.raises(ValueError):
        SpatialFilter(aoi=_valid_aoi(), predicate="within_distance")


def test_spatial_filter_nearest_requires_positive_int_k():
    with pytest.raises(ValueError):
        SpatialFilter(aoi=_valid_aoi(), predicate="nearest", k=0)


# ---------------------------------------------------------------------------
# FileSpatialAdapter per-format reads
# (one test per format the adapter must handle)
# ---------------------------------------------------------------------------

def test_file_adapter_read_shp():
    gdf = FileSpatialAdapter().read(path=SHP, read_options=ReadOptions())
    assert isinstance(gdf, gpd.GeoDataFrame)
    assert not gdf.empty


def test_file_adapter_read_gpkg():
    gdf = FileSpatialAdapter().read(path=GPKG, read_options=ReadOptions())
    assert isinstance(gdf, gpd.GeoDataFrame)
    assert not gdf.empty


def test_file_adapter_read_geojson():
    gdf = FileSpatialAdapter().read(path=GEOJSON, read_options=ReadOptions())
    assert isinstance(gdf, gpd.GeoDataFrame)
    assert not gdf.empty


def test_file_adapter_read_kml():
    gdf = FileSpatialAdapter().read(path=KML, read_options=ReadOptions())
    assert isinstance(gdf, gpd.GeoDataFrame)
    assert not gdf.empty


def test_file_adapter_read_kmz():
    gdf = FileSpatialAdapter().read(path=KMZ, read_options=ReadOptions())
    assert isinstance(gdf, gpd.GeoDataFrame)
    assert not gdf.empty


# ---------------------------------------------------------------------------
# FileSpatialAdapter ReadOptions features
# (spatial_filter, keep_columns, definition_query)
# ---------------------------------------------------------------------------

def test_file_adapter_spatial_filter():
    """Push an AOI down to the read and confirm consume-and-clear."""
    aoi = gpd.read_file(SHP)
    opts = ReadOptions(spatial_filter=SpatialFilter(aoi=aoi, predicate="intersects"))
    gdf = FileSpatialAdapter().read(path=SHP, read_options=opts)
    assert not gdf.empty
    # adapter consumed the filter so the base post-filter does not re-apply it
    assert opts.spatial_filter is None


def test_file_adapter_keep_columns():
    opts = ReadOptions(keep_columns=["Name"])
    gdf = FileSpatialAdapter().read(path=SHP, read_options=opts)
    assert set(gdf.columns) == {"Name", "geometry"}


def test_file_adapter_definition_query():
    """Pandas-query filter applied after the read."""
    match = FileSpatialAdapter().read(
        path=SHP,
        read_options=ReadOptions(definition_query='Name == "Test Shape A"'),
    )
    assert len(match) == 1

    no_match = FileSpatialAdapter().read(
        path=SHP,
        read_options=ReadOptions(definition_query='Name == "no such shape"'),
    )
    assert len(no_match) == 0
