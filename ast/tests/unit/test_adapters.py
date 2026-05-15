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
import geopandas as gpd
from pathlib import Path

DATA_DIR = Path('tests/data')
KML = 'Test_Shape_A.kml'

pytestmark = pytest.mark.unit

@pytest.mark.unit
def test_read():
    from core.data_adapters.kml.adapter import KMLAdapter
    source = DATA_DIR / KML
    # TODO: test kml adapter
    #da = KMLAdapter.read()
    #assert (da.area > 0)



    