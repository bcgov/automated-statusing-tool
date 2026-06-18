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
    - A lat/long AOI is rejected (distances need metres) -> EPSG 4326


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
from ast_engine.core.aoi.aoi_builder import AOIBuilder, AOIRequest, AreaOfInterest
from ast_engine.core.data_adapters.file.adapter import FileSpatialAdapter, SpatialFilter
from ast_engine.core.operator.proximity import (
    within_distance, nearest, _require_projected, _default_read_options 
)


# Test data folder + one data source per scenario 
# 
DATA_DIR = Path(__file__).parents[1] / "data" 
SHP = DATA_DIR / "Test_Shape_A" / "Test_Shape_A_shp" / "Test_Shape_A.shp"

THREEM =  DATA_DIR / "Test_Proximity" / "proximity_3_m.shp"
TENM =  DATA_DIR / "Test_Proximity" / "proximity_10_m.shp" 
TWOKM =  DATA_DIR / "Test_Proximity" / "proximity_2_km.shp"
MULTIPOINT = DATA_DIR / "Test_Proximity" / "proximity_points.shp"
NOCRS = DATA_DIR / "Test_Proximity" / "proximity_point_no_crs.shp"

# Tags every test in this file as "unit"
# replaces a per-function @pytest.mark.unit decorator on each test
pytestmark = pytest.mark.unit


def _valid_aoi() -> AreaOfInterest:
    """Create a projected AOI for proximity operator tests."""
    gdf = gpd.read_file(SHP)
    request = AOIRequest(aoi_id="test_aoi", name="Test AOI")
    aoi =  AOIBuilder().from_gdf(request, gdf)
    return aoi

def non_valid_aoi() -> AreaOfInterest:
    """Create a projected AOI for proximity operator tests."""
    gdf = gpd.read_file(NOCRS)
    request = AOIRequest(aoi_id="test_aoi", name="Test AOI")
    aoi =  AOIBuilder().from_gdf(request, gdf)
    return aoi

def test_3_within_distance():
    """Feed the proximity operator a point at a known distance (3m)
    Verify that the operator reads this distance correclty """
    test  = within_distance(
        aoi=_valid_aoi(),
        adapter=FileSpatialAdapter(),  # This would be a mock or fixture in a real test
        distance_m=12,
        feature_id_field="id",
        keep_properties=["name"],
        path = THREEM,
    )
    #This is rounded because my test data has some crazy trailing decimals 
    assert round((test.measure_value), 2) == 3.0

def test_10_within_distance():
    """Feed the proximity operator a point at a known distance (10m)
    Verify that the operator reads this distance correclty """
    test = within_distance(
        aoi=_valid_aoi(),
        adapter=FileSpatialAdapter(),
        distance_m=12,
        feature_id_field="id",
        keep_properties=["name"],
        path = TENM,
    )
    #This is rounded because my test data has some crazy trailing decimals 
    assert round((test.measure_value), 2) == 10.0

def test_2000_within_distance():
    """Feed the proximity operator a point at a known distance (2km)
    Verify that the operator reads this distance correclty """
    test = within_distance(
        aoi=_valid_aoi(),
        adapter=FileSpatialAdapter(),
        distance_m=3000,
        feature_id_field="id",
        keep_properties=["name"],
        path = TWOKM,
    )
    #This is rounded because my test data has some crazy trailing decimals 
    assert round((test.measure_value), 2) == 1999.25

def test_nearest_k():
    """
    Put 12m in and ensure that the 3 and 10 m points are returned, 
    in that order, with the right distance measures.
    """
    test = nearest(
        aoi = _valid_aoi(),
        adapter=FileSpatialAdapter(),
        k=2,
        max_distance_m = 12,
        path = MULTIPOINT,
    )

    assert test.feature_count == 2

    #This expected value is the shorter of the two (which we know is 3)
    assert round(test.measure_value, 2) == 3.00


def test_default_read_options():
    """
    Not sure what this one should do!
    """
    # test = _default_read_options(
    #         spatial_filter=,
    #         feature_id_field=,
    #         keep_properties=            
    # )
    pass


def test_build_results():
    test = within_distance(
        aoi=_valid_aoi(),
        adapter=FileSpatialAdapter(),
        distance_m=12,
        feature_id_field="FID",
        keep_properties=["Colour"],
        path = MULTIPOINT,
    )
    
    #This I want to use to make sure that all the FIDs, Colours and GDF are returned
    # That will implicitly test extract_feature_id and extract_properties
    #return test 





