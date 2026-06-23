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

from ast_engine.core.data_adapters.file.adapter import (
    FileSpatialAdapter,
    _split_datasource,
    _normalize_geometry_type,
)
from ast_engine.core.data_adapters.base import ReadOptions, SpatialFilter
from ast_engine.config.registry.query import definition_to_where


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
    """Read with a SpatialFilter on the ReadOptions."""
    aoi = gpd.read_file(SHP)
    opts = ReadOptions(spatial_filter=SpatialFilter(aoi=aoi, predicate="intersects"))
    gdf = FileSpatialAdapter().read(path=SHP, read_options=opts)
    assert not gdf.empty


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


def test_file_adapter_where_filter():
    """The structured where filter is compiled to SQLite and applied after the
    read, keeping the geometry intact."""
    match = FileSpatialAdapter().read(
        path=SHP,
        read_options=ReadOptions(where=definition_to_where("\"Name\" = 'Test Shape A'")),
    )
    assert len(match) == 1
    assert match.geometry.notna().all()

    no_match = FileSpatialAdapter().read(
        path=SHP,
        read_options=ReadOptions(where=definition_to_where("\"Name\" = 'no such shape'")),
    )
    assert len(no_match) == 0


# ---------------------------------------------------------------------------
# FileSpatialAdapter.describe() - metadata without a full read
# (one test per format; Test_Shape_A is a single polygon in every format,
# EPSG:3005 except KML/KMZ which are EPSG:4326. KML/KMZ report "Unknown" from
# GDAL, so they also exercise the one-feature geometry-type fallback.)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "path, expected_crs",
    [
        (SHP, "EPSG:3005"),
        (GPKG, "EPSG:3005"),
        (GEOJSON, "EPSG:3005"),
        (KML, "EPSG:4326"),
        (KMZ, "EPSG:4326"),
    ],
)
def test_file_adapter_describe(path, expected_crs):
    info = FileSpatialAdapter().describe(path=path)
    assert info.geometry_type == "polygon"
    assert info.crs == expected_crs
    assert "Name" in info.columns
    assert info.geom_column
    assert info.row_count == 1


def test_file_adapter_describe_gpkg_with_layer():
    """A GeoPackage datasource that names its layer is split, then inspected."""
    info = FileSpatialAdapter().describe(path=f"{GPKG}/Test_Shape_A")
    assert info.geometry_type == "polygon"
    assert info.crs == "EPSG:3005"


def test_file_adapter_read_gpkg_with_layer():
    """The same combined path/layer string also reads through to features."""
    gdf = FileSpatialAdapter().read(
        path=f"{GPKG}/Test_Shape_A", read_options=ReadOptions()
    )
    assert not gdf.empty


# ---------------------------------------------------------------------------
# Datasource path / layer splitting
# (the registry stores one string; the adapter splits the file path from the
# optional layer. Pure string tests - no files are read.)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "datasource, expected",
    [
        # file geodatabase with a layer (forward + back slashes)
        ("W:/data/foo.gdb/roads", ("W:/data/foo.gdb", "roads")),
        (r"W:\data\foo.gdb\roads", (r"W:\data\foo.gdb", "roads")),
        # geopackage with a layer
        ("W:/data/foo.gpkg/lakes", ("W:/data/foo.gpkg", "lakes")),
        # UNC path with a layer
        (r"\\server\share\foo.gdb\rivers", (r"\\server\share\foo.gdb", "rivers")),
        # feature class inside a feature dataset -> layer is the last segment
        # (GDAL addresses the feature class by name; the feature dataset is
        # not part of the layer path)
        ("W:/data/foo.gdb/dataset/roads", ("W:/data/foo.gdb", "roads")),
        (r"\\server\share\foo.gdb\dataset\roads", (r"\\server\share\foo.gdb", "roads")),
        # container with no layer -> default / only layer
        ("W:/data/foo.gdb", ("W:/data/foo.gdb", None)),
        ("W:/data/foo.gdb/", ("W:/data/foo.gdb", None)),
        # flat files -> whole string, no layer
        ("C:/data/bar.shp", ("C:/data/bar.shp", None)),
        ("C:/data/bar.geojson", ("C:/data/bar.geojson", None)),
        ("C:/data/bar.kml", ("C:/data/bar.kml", None)),
        ("C:/data/bar.kmz", ("C:/data/bar.kmz", None)),
        # case-insensitive extension
        ("W:/data/FOO.GDB/Roads", ("W:/data/FOO.GDB", "Roads")),
        ("W:/data/foo.GPKG/lakes", ("W:/data/foo.GPKG", "lakes")),
        # mixed forward / back slashes
        (r"W:\data/foo.gdb/roads", (r"W:\data/foo.gdb", "roads")),
    ],
)
def test_split_datasource(datasource, expected):
    assert _split_datasource(datasource) == expected


# ---------------------------------------------------------------------------
# Geometry-type normalization (GDAL names -> point/line/polygon)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "name, expected",
    [
        ("Point", "point"),
        ("MultiPoint", "point"),
        ("3D Point", "point"),
        ("LineString", "line"),
        ("MultiLineString", "line"),
        ("Polygon", "polygon"),
        ("Polygon Z", "polygon"),
        ("MultiPolygon", "polygon"),
        ("Unknown", None),
        ("GeometryCollection", None),
        (None, None),
    ],
)
def test_normalize_geometry_type(name, expected):
    assert _normalize_geometry_type(name) == expected
