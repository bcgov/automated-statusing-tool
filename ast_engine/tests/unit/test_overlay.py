
"""
--------------------------------------------------------------------------
Overlay operator test

Purpose:
- Feed the operator simple geometry with known overlap:
    - 3 polygons
    - 3 polylines
- Check:
    - Intersection is calculated correctly
    - Per-feature overlap (area/length) is correct
    - Features are sorted by overlap (descending)
    - Totals are summed correctly
    - Properties and feature IDs are handled correctly
    - Non-overlapping features are dropped
    - Invalid AOIs are rejected

Examples: 




--------------------------------------------------------------------------
"""

import pytest
from pathlib import Path
import geopandas as gpd

from ast_engine.core.aoi.aoi_builder import AOIBuilder, AOIRequest, AreaOfInterest
from ast_engine.core.data_adapters.base import BaseSpatialAdapter, DatasetInfo
from ast_engine.core.data_adapters.file.adapter import FileSpatialAdapter
from ast_engine.core.operator.overlay import (
    intersection, _default_read_options, _require_projected
)

# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).parents[1] / "data"
SHP = DATA_DIR / "Test_Shape_A" / "Test_Shape_A_shp" / "Test_Shape_A.shp"


"""Data Structures are as follows.
3 points, one inside Test Shape A, one on on the vertice, one well outside
100m buffer around each of these points makes polygons layer - each has total area of ~3.14 ha. 
A polyline that roughly bisects polygons for 200m length total. """
POINTS   = DATA_DIR / "Test_Overlay" / "points.shp"
POLYGONS = DATA_DIR / "Test_Overlay" / "polygons.shp"
POLYLINES = DATA_DIR / "Test_Overlay" / "polylines.shp"


pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _valid_aoi() -> AreaOfInterest:
    """Uses the aoi builder to create a valid AOI for consumption in the operator tests
    """
    gdf = gpd.read_file(SHP)
    request = AOIRequest(aoi_id="test_aoi", name="Test AOI")
    return AOIBuilder().from_gdf(request, gdf)


def non_valid_aoi() -> AreaOfInterest:
    """
    Create a non valid aoi for testing of checks in the operator
    """
    aoi = _valid_aoi()
    aoi.gdf = aoi.gdf.to_crs(4326)
    return aoi

def test_polygon_overlap_exact_values():
    """3 polygons: inside, partial, outside → total area check.
    Area is 3.14 for full polygon, Second polygon overlaps by one quarter (.78 ha)"""
    test = intersection(
        aoi=_valid_aoi(),
        adapter=FileSpatialAdapter(),
        keep_properties=["Name"],
        path=POLYGONS,
    )

    assert test.feature_count == 2  # outside dropped

    # Expected: 3.14 + 0.78 = 3.92 (with rounding)
    assert round((test.total_area/10000), 2) == 3.92

    # Sorted largest → smallest
    measures = [round(f.measure, 2) for f in test.features]
    assert measures == sorted(measures, reverse=True)


def test_line_overlap_exact_values():
    """3 lines: inside, crossing, outside → total length check
    First line fully intersects (200m), second only partiall(100m)"""
    test = intersection(
        aoi=_valid_aoi(),
        adapter=FileSpatialAdapter(),
        path=POLYLINES,
    )

    assert test.feature_count == 2

    # Expected: 200 + ~100
    assert round(test.total_length, 0) == 300

    measures = [round(f.measure, 0) for f in test.features]
    assert measures == sorted(measures, reverse=True)


def test_point_overlay_count():
    """Points inside AOI are counted, no measure."""
    test = intersection(
        aoi=_valid_aoi(),
        adapter=FileSpatialAdapter(),
        path=POINTS,
    )

    assert test.feature_count == 2
    assert all(f.measure is None for f in test.features)


# ---------------------------------------------------------------------------
# Sorting behaviour
# ---------------------------------------------------------------------------

def test_sorted_descending_by_overlap():
    test = intersection(
        aoi=_valid_aoi(),
        adapter=FileSpatialAdapter(),
        path=POLYGONS,
    )

    measures = [f.measure for f in test.features]
    assert measures == sorted(measures, reverse=True)


# ---------------------------------------------------------------------------
# Filtering behaviour
# ---------------------------------------------------------------------------

def test_zero_overlap_removed():
    """Outside features never appear in results."""
    test = intersection(
        aoi=_valid_aoi(),
        adapter=FileSpatialAdapter(),
        path=POLYGONS,
    )

    assert all(f.measure > 0 for f in test.features)


# ---------------------------------------------------------------------------
# Attribute + ID handling
# ---------------------------------------------------------------------------

def test_properties_preserved():
    test = intersection(
        aoi=_valid_aoi(),
        adapter=FileSpatialAdapter(),
        keep_properties=["Name"],
        path=POLYGONS,
    )

    names = [f.properties["Name"] for f in test.features]
    assert len(names) == test.feature_count
    assert all(name is not None for name in names)


def test_feature_id_fallback():
    test = intersection(
        aoi=_valid_aoi(),
        adapter=FileSpatialAdapter(),
        feature_id_field="NOT_REAL",
        path=POLYGONS,
    )

    ids = [f.feature_id for f in test.features]
    assert len(set(ids)) == len(ids)


# ---------------------------------------------------------------------------
# Internal logic
# ---------------------------------------------------------------------------

def test_default_read_options_overlay():
    opts = _default_read_options(
        aoi=_valid_aoi(),
        feature_id_field="Id",
        keep_properties=["Type"],
    )

    assert opts.spatial_filter.predicate == "intersects"
    assert set(opts.keep_columns) == {"Id", "Type"}

    
def test_build_results():
    """Check kept columns (Colour) and feature IDs come back on the result.
    "FID" is not a real column here, so the feature_id falls back to the row number."""
    test = intersection(
        aoi=_valid_aoi(),
        adapter=FileSpatialAdapter(),
        distance_m=12,
        feature_id_field="FID",
        keep_properties=["Name"],
        path = POINTS,
    )
    # extract_properties: the Colour column comes through (3 m point then 10 m point)
    assert [f.properties.get("Name") for f in test.features] == ["First", "Second"]
    # extract_feature_id: no real "FID" column, so IDs fall back to distinct row numbers
    assert len({f.feature_id for f in test.features}) == 2


# ---------------------------------------------------------------------------
# CRS validation
# ---------------------------------------------------------------------------

def test_non_projected_aoi_rejected():
    with pytest.raises(ValueError):
        intersection(
            aoi=non_valid_aoi(),
            adapter=FileSpatialAdapter(),
            path=POLYGONS,
        )

# ---------------------------------------------------------------------------
# Fake Adapter to test empty cases! 
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Adapter behaviour
# ---------------------------------------------------------------------------

def test_operator_pushes_intersects():
    adapter = RecordingAdapter()

    intersection(
        aoi=_valid_aoi(),
        adapter=adapter,
        path=POLYGONS,
    )

    sf = adapter.last_options.spatial_filter
    assert sf.predicate == "intersects"


# ---------------------------------------------------------------------------
# Empty result
# ---------------------------------------------------------------------------

def test_empty_returns_zero_area():
    adapter = RecordingAdapter()

    test = intersection(
        aoi=_valid_aoi(),
        adapter=adapter,
        geom_type="polygon",
        path=POLYGONS,
    )

    assert test.total_area == 0.0
    assert test.features == []
