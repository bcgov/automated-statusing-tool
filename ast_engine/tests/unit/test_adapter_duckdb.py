#\tests\unit\test_adapters.py
"""
DuckDB adapter tests

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
def test_duckdb_adapter_read()

"""
import pytest
from pathlib import Path
import geopandas as gpd

from ast_engine.core.data_adapters.duckdb.adapter import (
    DuckDBAdapter,
    DuckDBConfig
)
from ast_engine.core.data_adapters.base import ReadOptions


# Test data folder + one constant per supported format.
# adapter must read. shp / gpkg / geojson are EPSG:3005, kml is EPSG:4326.
DATA_DIR = Path(__file__).parents[1] / "data"
SHP = DATA_DIR / "Test_Shape_A" / "Test_Shape_A_shp" / "Test_Shape_A.shp"
GEOPARQUET_FILE = "WHSE_CADASTRE_PMBC_PARCEL_FABRIC_POLY_FA_SVW.parquet"
GEOPARQUET_SOURCE = DATA_DIR / "Test_Data_PMBC_PARCEL_FABRIC_geoparquet" / GEOPARQUET_FILE
DUCKDB_CONFIG = DuckDBConfig()

# Tags every test in this file as "unit"
# replaces a per-function @pytest.mark.unit decorator on each test
pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# FileSpatialAdapter per-format reads
# (one test per format the adapter must handle)
# ---------------------------------------------------------------------------
def test_duckdb_adapter_creation():
    adapter = DuckDBAdapter(config= DUCKDB_CONFIG)
    assert isinstance(adapter, DuckDBAdapter)

def test_duckdb_adapter_read():
    adapter = DuckDBAdapter(config= DUCKDB_CONFIG)
    gdf = adapter.read(source=str(GEOPARQUET_SOURCE))
    assert isinstance(gdf, gpd.GeoDataFrame)
    assert not gdf.empty

# ---------------------------------------------------------------------------
# FileSpatialAdapter ReadOptions features
# (spatial_filter, keep_columns, definition_query)
# ---------------------------------------------------------------------------

# def test_file_adapter_spatial_filter():
#     """Read with a SpatialFilter on the ReadOptions."""
#     aoi = gpd.read_file(SHP)
#     opts = ReadOptions(spatial_filter=SpatialFilter(aoi=aoi, predicate="intersects"))
#     gdf = FileSpatialAdapter().read(path=SHP, read_options=opts)
#     assert not gdf.empty


# def test_file_adapter_keep_columns():
#     opts = ReadOptions(keep_columns=["Name"])
#     gdf = FileSpatialAdapter().read(path=SHP, read_options=opts)
#     assert set(gdf.columns) == {"Name", "geometry"}


# def test_file_adapter_definition_query():
#     """Pandas-query filter applied after the read."""
#     match = FileSpatialAdapter().read(
#         path=SHP,
#         read_options=ReadOptions(definition_query='Name == "Test Shape A"'),
#     )
#     assert len(match) == 1

#     no_match = FileSpatialAdapter().read(
#         path=SHP,
#         read_options=ReadOptions(definition_query='Name == "no such shape"'),
#     )
#     assert len(no_match) == 0


# def test_file_adapter_where_filter():
#     """The structured where filter is compiled to SQLite and applied after the
#     read, keeping the geometry intact."""
#     match = FileSpatialAdapter().read(
#         path=SHP,
#         read_options=ReadOptions(where=definition_to_where("\"Name\" = 'Test Shape A'")),
#     )
#     assert len(match) == 1
#     assert match.geometry.notna().all()

#     no_match = FileSpatialAdapter().read(
#         path=SHP,
#         read_options=ReadOptions(where=definition_to_where("\"Name\" = 'no such shape'")),
#     )
#     assert len(no_match) == 0


# ---------------------------------------------------------------------------
# DuckDBAdapter.describe() - metadata without a full read
# ---------------------------------------------------------------------------

def test_duckdb_adapter_describe():
    adapter = DuckDBAdapter(config= DUCKDB_CONFIG)
    info = adapter.describe(source=str(GEOPARQUET_SOURCE))
    assert info.geometry_type == "polygon"
    assert info.crs == "EPSG:3005"
    assert "PID" in info.columns
    assert info.geom_column
    assert info.row_count == 513

