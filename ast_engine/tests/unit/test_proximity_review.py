"""
--------------------------------------------------------------------------
TEMPORARY COMMENT - DELETE FROM PUBLISHING:
This file is based on Jordan Proximity Tests, edited by Moez to add more test cases 
and cover more of the operator's functionality. 
The original tests are still here, but new ones have been added 

--------------------------------------------------------------------------




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

from ast_engine.core.aoi.aoi_builder import AOIBuilder, AOIRequest, AreaOfInterest
from ast_engine.core.data_adapters.base import BaseSpatialAdapter, DatasetInfo
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
    """Create a NON-projected (lat/long) AOI to check the operator rejects it.

    The AOI builder always converts to BC Albers, so we build a normal AOI and
    switch it back to lat/long (EPSG:4326) by hand. (The no-CRS file can't be
    used here - the builder rejects a layer with no CRS before the operator runs.)
    """
    aoi = _valid_aoi()
    aoi.gdf = aoi.gdf.to_crs(4326)
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
    """_default_read_options pushes the spatial filter down and keeps the columns
    the operator needs (the id field plus any properties we asked to keep)."""
    sf = SpatialFilter(aoi=_valid_aoi().gdf, predicate="within_distance", distance=12)
    opts = _default_read_options(sf, "Id", ["Colour"])
    assert opts.spatial_filter is sf
    assert set(opts.keep_columns) == {"Id", "Colour"}


def test_build_results():
    """Check kept columns (Colour) and feature IDs come back on the result.
    "FID" is not a real column here, so the feature_id falls back to the row number."""
    test = within_distance(
        aoi=_valid_aoi(),
        adapter=FileSpatialAdapter(),
        distance_m=12,
        feature_id_field="FID",
        keep_properties=["Colour"],
        path = MULTIPOINT,
    )
    # extract_properties: the Colour column comes through (3 m point then 10 m point)
    assert [f.properties.get("Colour") for f in test.features] == ["Green", "Blue"]
    # extract_feature_id: no real "FID" column, so IDs fall back to distinct row numbers
    assert len({f.feature_id for f in test.features}) == 2


# ---------------------------------------------------------------------------
# Added by Moez - cover adddiotnal tests (far points, ordering, caps, bad input,
# non-projected AOI, and that the operator asks the source for the right search).
# ---------------------------------------------------------------------------

def test_far_point_excluded():
    """A point further than the search distance is dropped; empty result reports 0."""
    test = within_distance(
        aoi=_valid_aoi(), adapter=FileSpatialAdapter(), distance_m=5, path=TENM,
    )
    assert test.feature_count == 0
    assert test.measure_value == 0.0


def test_within_distance_keeps_closest_first():
    """All three points in one layer: distance 12 keeps the 3 m + 10 m points, closest first."""
    test = within_distance(
        aoi=_valid_aoi(), adapter=FileSpatialAdapter(), distance_m=12, path=MULTIPOINT,
    )
    assert test.feature_count == 2
    assert [round(f.measure, 2) for f in test.features] == [3.0, 10.0]


def test_nearest_k_limits_count():
    """k=1 returns only the single closest point."""
    test = nearest(aoi=_valid_aoi(), adapter=FileSpatialAdapter(), k=1, path=MULTIPOINT)
    assert test.feature_count == 1
    assert round(test.measure_value, 2) == 3.0


def test_nearest_max_distance_cap():
    """Ask for the 2 nearest but cap at 5 m - only the 3 m point qualifies."""
    test = nearest(
        aoi=_valid_aoi(), adapter=FileSpatialAdapter(), k=2, max_distance_m=5, path=MULTIPOINT,
    )
    assert test.feature_count == 1
    assert round(test.measure_value, 2) == 3.0


def test_negative_distance_raises():
    with pytest.raises(ValueError):
        within_distance(aoi=_valid_aoi(), adapter=FileSpatialAdapter(), distance_m=-1, path=THREEM)


def test_nearest_k_below_one_raises():
    with pytest.raises(ValueError):
        nearest(aoi=_valid_aoi(), adapter=FileSpatialAdapter(), k=0, path=MULTIPOINT)


def test_negative_max_distance_raises():
    with pytest.raises(ValueError):
        nearest(aoi=_valid_aoi(), adapter=FileSpatialAdapter(), k=1, max_distance_m=-1, path=MULTIPOINT)


def test_non_valid_aoi_rejected():
    """A lat/long AOI (degrees) is refused - distances must be in metres."""
    with pytest.raises(ValueError):
        within_distance(aoi=non_valid_aoi(), adapter=FileSpatialAdapter(), distance_m=12, path=THREEM)


class RecordingAdapter(BaseSpatialAdapter):
    """A stand-in data source that remembers what the operator asked it for.

    It does not read a file - it stores the read_options it was handed and
    returns an empty result, so we can confirm the operator asks for the right
    search (within_distance vs nearest, with the right distance / k).
    """

    def __init__(self):
        self.last_options = None

    def read(self, *, read_options=None, target_crs=None, **source_kwargs):
        self.last_options = read_options
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:3005")

    def _read_impl(self, *, read_options, **source_kwargs):
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:3005")

    def describe(self, **source_kwargs) -> DatasetInfo:
        raise NotImplementedError


def test_within_distance_asks_for_within_distance_search():
    adapter = RecordingAdapter()
    within_distance(aoi=_valid_aoi(), adapter=adapter, distance_m=12, path=THREEM)
    sf = adapter.last_options.spatial_filter
    assert sf.predicate == "within_distance"
    assert sf.distance == 12


def test_nearest_asks_for_nearest_search():
    adapter = RecordingAdapter()
    nearest(aoi=_valid_aoi(), adapter=adapter, k=2, path=MULTIPOINT)
    sf = adapter.last_options.spatial_filter
    assert sf.predicate == "nearest"
    assert sf.k == 2
