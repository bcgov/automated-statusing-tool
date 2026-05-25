#\tests\unit\test_adapters.py
"""
File Based Adapter tests

Purpose:
- Each file based adapter must be tested
- Provide a simple test
    - spatial_mask
    - keep_columns
    - definition_query

HOW TO EXTEND:
-------------
1. Add a new test file for each file based adapter
2. Keep test names short and readable
3. Data must be synthetic or based from in local test data

Example:
test_data_adapters_kml.py
def test_read()
def test_defn_query()
def test_keep_columns()
def test_spatial_mask()

"""
import pytest
from pathlib import Path
from ast_engine.core.data_adapters.kml.adapter import KMLAdapter
from ast_engine.core.data_adapters.base import ReadOptions
import geopandas as gpd
# from shapely.geometry import Point
# from typing import Iterable


DATA_DIR = Path(__file__).parents[1] / "data" / "Test_Shape_A"
KML = DATA_DIR / "Test_Shape_A.kml"

pytestmark = pytest.mark.unit

@pytest.mark.unit
def test_kml_adapter_read():
    adapter = KMLAdapter()
    read_options = ReadOptions()
    adapter.read(path= KML, read_options=read_options)
    gdf = adapter._read_impl(path=KML, read_options=read_options)

    # Assert that the GeoDataFrame is created correctly
    assert isinstance(gdf, gpd.GeoDataFrame)
    # Assert geodatafram has features



    