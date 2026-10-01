"""
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
    - With an AOI of two rows, both give one result per row, and nearest
      searches once per row (its nearest feature and distance are per row)


HOW TO EXTEND:
-------------
1. Add a new test function per scenario the operator must handle
2. Keep test names short and readable
3. Reuse the data already in tests/data/


Example:
def test_3_within_distance()
def test_10_within_distance()
def test_2000_within_distance()
def test_nearest_k()
def test_default_read_options()
def test_build_results()
def test_far_point_excluded()
def test_within_distance_keeps_closest_first()
def test_nearest_k_limits_count()
def test_nearest_max_distance_cap()

Note: the operators return an OperatorOutcome - one result per AOI part, plus the
features each was built from. The test AOIs here are one row, so one part:
the tests read `.parts[0].result` off the call.

"""

import pytest
from pathlib import Path
import geopandas as gpd
from shapely.geometry import box

from ast_engine.core.aoi.aoi_builder import AOIBuilder, AOIRequest, AreaOfInterest
from ast_engine.core.data_adapters.base import BaseSpatialAdapter, DatasetInfo
from ast_engine.core.data_adapters.file.adapter import FileSpatialAdapter, SpatialFilter
from ast_engine.core.operator.proximity import (
    within_distance, nearest, _default_read_options 
)


# Test data folder + one data source per scenario 
# 
DATA_DIR = Path(__file__).parents[1] / "data" 
SHP = DATA_DIR / "Test_Shape_A" / "Test_Shape_A_shp" / "Test_Shape_A.shp"

THREEM =  DATA_DIR / "Test_Proximity" / "proximity_3_m.shp"
TENM =  DATA_DIR / "Test_Proximity" / "proximity_10_m.shp" 
TWOKM =  DATA_DIR / "Test_Proximity" / "proximity_2_km.shp"
MULTIPOINT = DATA_DIR / "Test_Proximity" / "proximity_points.shp"


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
    Verify that the operator reads this distance correctly """
    test  = within_distance(
        aoi=_valid_aoi(),
        adapter=FileSpatialAdapter(),  # This would be a mock or fixture in a real test
        distance_m=12,
        feature_id_field="id",
        keep_properties=["name"],
        path = THREEM,
    ).parts[0].result
    #This is rounded because test data has some trailing decimals 
    assert round((test.measure_value), 2) == 3.0

def test_10_within_distance():
    """Feed the proximity operator a point at a known distance (10m)
    Verify that the operator reads this distance correctly """
    test = within_distance(
        aoi=_valid_aoi(),
        adapter=FileSpatialAdapter(),
        distance_m=12,
        feature_id_field="id",
        keep_properties=["name"],
        path = TENM,
    ).parts[0].result
    #This is rounded because test data has some trailing decimals 
    assert round((test.measure_value), 2) == 10.0

def test_2000_within_distance():
    """Feed the proximity operator a point at a known distance (2km)
    Verify that the operator reads this distance correctly """
    test = within_distance(
        aoi=_valid_aoi(),
        adapter=FileSpatialAdapter(),
        distance_m=3000,
        feature_id_field="id",
        keep_properties=["name"],
        path = TWOKM,
    ).parts[0].result
    #This is rounded because test data has some trailing decimals 
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
    ).parts[0].result

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


def test_build_results_within_distance():
    """Check kept columns (Colour) and feature IDs come back on the result.
    "FID" is not a real column here, so the feature_id falls back to the row number."""
    test = within_distance(
        aoi=_valid_aoi(),
        adapter=FileSpatialAdapter(),
        distance_m=12,
        feature_id_field="FID",
        keep_properties=["Colour"],
        path = MULTIPOINT,
    ).parts[0].result
    # extract_properties: the Colour column comes through (3 m point then 10 m point)
    assert [f.properties.get("Colour") for f in test.features] == ["Green", "Blue"]
    # extract_feature_id: no real "FID" column, so IDs fall back to distinct row numbers
    assert len({f.feature_id for f in test.features}) == 2

def test_build_results_nearest():
    """Check kept columns (Colour) and feature IDs come back on the result.
    "FID" is not a real column here, so the feature_id falls back to the row number."""
    test = nearest(
        aoi=_valid_aoi(),
        adapter=FileSpatialAdapter(),
        k=2,
        feature_id_field="FID",
        keep_properties=["Colour"],
        path = MULTIPOINT,
    ).parts[0].result
    # extract_properties: the Colour column comes through (3 m point then 10 m point)
    assert [f.properties.get("Colour") for f in test.features] == ["Green", "Blue"]
    # extract_feature_id: no real "FID" column, so IDs fall back to distinct row numbers
    assert len({f.feature_id for f in test.features}) == 2



# ---------------------------------------------------------------------------
# Added by Moez - cover addditional tests (far points, ordering, caps, bad input,
# non-projected AOI, and that the operator asks the source for the right search).
# ---------------------------------------------------------------------------

def test_far_point_excluded():
    """A point further than the search distance is dropped; empty result reports 0."""
    test = within_distance(
        aoi=_valid_aoi(), adapter=FileSpatialAdapter(), distance_m=5, path=TENM,
    ).parts[0].result
    assert test.feature_count == 0
    assert test.measure_value == 0.0


def test_within_distance_keeps_closest_first():
    """All three points in one layer: distance 12 keeps the 3 m + 10 m points, closest first."""
    test = within_distance(
        aoi=_valid_aoi(), adapter=FileSpatialAdapter(), distance_m=12, path=MULTIPOINT,
    ).parts[0].result
    assert test.feature_count == 2
    assert [round(f.measure, 2) for f in test.features] == [3.0, 10.0]


def test_nearest_k_limits_count():
    """k=1 returns only the single closest point."""
    test = nearest(aoi=_valid_aoi(), adapter=FileSpatialAdapter(), k=1, path=MULTIPOINT).parts[0].result
    assert test.feature_count == 1
    assert round(test.measure_value, 2) == 3.0


def test_nearest_max_distance_cap():
    """Ask for the 2 nearest but cap at 5 m - only the 3 m point qualifies."""
    test = nearest(
        aoi=_valid_aoi(), adapter=FileSpatialAdapter(), k=2, max_distance_m=5, path=MULTIPOINT,
    ).parts[0].result
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
        self.all_options = []

    def read(self, *, read_options=None, target_crs=None, **source_kwargs):
        self.last_options = read_options
        self.all_options.append(read_options)
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


def _two_row_aoi() -> AreaOfInterest:
    """The AOI box cut into a west and an east half, kept as two rows (two parts)."""
    minx, miny, maxx, maxy = _valid_aoi().gdf.total_bounds
    mid = (minx + maxx) / 2
    halves = [box(minx, miny, mid, maxy), box(mid, miny, maxx, maxy)]
    gdf = gpd.GeoDataFrame({"label": ["west", "east"]}, geometry=halves, crs="EPSG:3005")
    request = AOIRequest(aoi_id="test_aoi", name="Two rows", dissolve_mode="preserve_features")
    return AOIBuilder().from_gdf(request, gdf)


def test_nearest_is_found_for_each_part():
    """With two rows, nearest gives each part its OWN nearest feature and distance.
    The Green point is 3 m from the west half but about 1.8 km from the east
    half - a single search against the whole AOI would only report the 3 m."""
    aoi = _two_row_aoi()
    within = within_distance(aoi=aoi, adapter=FileSpatialAdapter(), distance_m=12, path=MULTIPOINT)
    near = nearest(aoi=aoi, adapter=FileSpatialAdapter(), k=1, keep_properties=["Colour"], path=MULTIPOINT)

    assert [p.aoi_part_id for p in within.parts] == ["test_aoi_part_1", "test_aoi_part_2"]
    assert [p.aoi_part_id for p in near.parts] == ["test_aoi_part_1", "test_aoi_part_2"]
    west, east = (p.result for p in near.parts)
    assert [f.properties["Colour"] for f in west.features] == ["Green"]
    assert west.measure_value == pytest.approx(3.0, abs=0.1)
    assert [f.properties["Colour"] for f in east.features] == ["Green"]
    assert east.measure_value == pytest.approx(1799.7, abs=0.1)


def test_nearest_searches_once_per_part():
    """nearest asks the source once per AOI part, each time for the nearest to that
    part only, and every search keeps the attribute filter (where)."""
    adapter = RecordingAdapter()
    where = {"conditions": [{"field": "Colour", "op": "=", "value": "Green"}]}
    aoi = _two_row_aoi()
    nearest(aoi=aoi, adapter=adapter, k=1, where=where, path=MULTIPOINT)

    assert len(adapter.all_options) == 2                       # one search per part
    searched = [options.spatial_filter.aoi for options in adapter.all_options]
    assert [len(part) for part in searched] == [1, 1]           # each against one part
    assert not searched[0].geometry.iloc[0].equals(searched[1].geometry.iloc[0])
    assert all(options.where == where for options in adapter.all_options)
