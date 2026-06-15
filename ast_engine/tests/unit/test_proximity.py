"""
(From Moez)
Feeds the operator a pretend data source with points at known distances 
(3 m, 10 m, 2 km from a 1 km AOI box) 
and checks: `within_distance(12)` keeps the 3 m + 10 m points (closest first) 
and reports 3 m; 
it asks the source for a `within_distance` filter; `nearest(k=2)` 
returns the 2 closest; nothing-found gives an empty result;
a lat/long AOI is rejected (distances need metres).

Proximity operator test 


Purpose:
- Feed the operator a pretend data source with known points at known distance 
    - 3m, 10m, 2km (from a 1km AOI box)
- Check that `within_distance(12)` keeps the 3 m + 10 m points (closest first)
- Ask the source to return the following: 
    - `within_distance(12)` returns the 3 m + 10 m points (closest first) and reports 3 m
    - `nearest(k=2)` returns the 2 closest points
    - Nothing-found gives an empty result
    - A lat/long AOI is rejected (distances need metres) ???


HOW TO EXTEND:
-------------
1. Add a new test function per scenario the operator must handle
2. Keep test names short and readable
3. Reuse the Test_Shape_A data already in tests/data/


Example:
def 
def 

"""

import pytest
from pathlib import Path
import geopandas as gpd

import pytest
from ast_engine.core.data_adapters.file.adapter import SpatialFileAdapter
from ast_engine.core.operator.proximity import (
    within_distance, _require_projected, _default_read_options 
)


# Test data folder + one data source per scenario 
# 
DATA_DIR = Path(__file__).parents[1] / "data" 
SHP = DATA_DIR / "Test_Shape_A" / "Test_Shape_A_shp" / "Test_Shape_A.shp"

THREEM =  DATA_DIR / "Test_Proximity" / "proximity_3_m.shp"
TENM =  DATA_DIR / "Test_Proximity" / "proximity_10_m.shp"
TWOKM =  DATA_DIR / "Test_Proximity" / "proximity_2_km.shp"

# Tags every test in this file as "unit"
# replaces a per-function @pytest.mark.unit decorator on each test
pytestmark = pytest.mark.unit


def _valid_aoi() -> gpd.GeoDataFrame:
    """Re-read the test shapefile as a projected AOI for SpatialFilter cases."""
    return gpd.read_file(SHP)

def test_3_within_distance():
    test   = within_distance(
        aoi=_valid_aoi(),
        adapter=SpatialFileAdapter(),  # This would be a mock or fixture in a real test
        distance_m=12,
        feature_id_field="id",
        keep_properties=["name"],
        source_kwargs={"path": "mock_source"},
    )

    print(test)
    
test_3_within_distance()


def test_10_within_distance():
    pass

def test_2000_within_distance():
    pass
    
def test_nearest_k():
    """
    Put 12m in and ensure that the 3 and 10 m points are returned, in that order, with the right distance measures.
    """
    pass

def test_default_read_options():
    pass

def test_require_projected():
    pass

def test_build_results():
    pass

def test_extract_feautre_id(): 
    pass 

def test_extract_properties():
    pass


