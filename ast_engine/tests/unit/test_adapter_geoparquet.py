"""
DuckDB GeoParquet adapter unit tests.

These test reading spatial datasets from GeoParquet files via DuckDB, 
matching the pattern of file and Oracle adapter tests.
"""

from pathlib import Path
import pytest
import geopandas as gpd

from ast_engine.core.data_adapters.duckdb.adapter import DuckDBAdapter, DuckDBConfig
from ast_engine.core.data_adapters.base import ReadOptions

pytestmark = pytest.mark.unit

DATA_DIR = Path(__file__).parents[1] / "data"
GEOPARQUET_FILE = (
    DATA_DIR
    / "Test_Data_PMBC_PARCEL_FABRIC_geoparquet"
    / "WHSE_CADASTRE_PMBC_PARCEL_FABRIC_POLY_FA_SVW.parquet"
)


def test_duckdb_adapter_reads_geoparquet_metadata():
    """Verify the adapter can inspect columns and metadata from a GeoParquet file."""
    if not GEOPARQUET_FILE.exists():
        pytest.skip("GeoParquet test dataset not present.")
    
    adapter = DuckDBAdapter(DuckDBConfig())
    desc = adapter.describe(source=str(GEOPARQUET_FILE))
    assert isinstance(desc.columns, list)
    assert len(desc.columns) > 0
    assert desc.row_count > 0
    assert desc.geom_column is not None

def test_duckdb_adapter_reads_geodataframe():
    """Verify reading features into a GeoDataFrame with a spatial filter or bounds."""
    if not GEOPARQUET_FILE.exists():
        pytest.skip("GeoParquet test dataset not present.")

    adapter = DuckDBAdapter(DuckDBConfig())
    
    # Read without filters first or with basic options matching BaseSpatialAdapter
    options = ReadOptions(keep_columns=["PARCEL_ID", "LAND_LEGAL_DESCRIPTION"])
    gdf = adapter.read(source=str(GEOPARQUET_FILE), options=options)

    assert isinstance(gdf, gpd.GeoDataFrame)
    assert not gdf.empty
    assert "geometry" in gdf.columns