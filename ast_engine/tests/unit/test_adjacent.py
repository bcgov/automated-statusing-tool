"""
Adjacency operator tests.

The adjacency operator measures how much of a dataset feature's boundary is
shared with the AOI boundary, and reports the total shared length.

These tests build small polygons against the AOI's edges with shapely and feed
them through a stand-in (fake) data source, so no shapefiles are needed - the
shared-edge lengths are exact and easy to read. The AOI is the Test_Shape_A box
(a rectangle in BC Albers / EPSG:3005).

What we check:
- a polygon sharing a full edge is adjacent, and the shared length is right;
- a corner-only touch is NOT adjacent (no shared line, just a point);
- a thin gap is missed with an exact touch but caught with a tolerance;
- an empty dataset is not adjacent;
- several adjacent polygons come back sorted longest-shared first, with their
  IDs and kept columns;
- bad input (negative tolerance) and a lat/long AOI are rejected;
- the operator asks the source for the right search (touches vs within_distance);
- with an AOI of two parts, only each part's outer edge counts: the edge the two
  parts share is inside the AOI.

Note: the operator returns an OperatorOutcome - one result per AOI part, plus the
features each was built from. The test AOIs here are one row, so one part:
the tests read `.parts[0].result` off the call (except the two-part test).
"""

import pytest
from pathlib import Path
import geopandas as gpd
from shapely.geometry import Polygon

from ast_engine.core.aoi.aoi_builder import AOIBuilder, AOIRequest, AreaOfInterest
from ast_engine.core.data_adapters.base import BaseSpatialAdapter, DatasetInfo
from ast_engine.core.operator.adjacent import adjacency

# Tags every test in this file as "unit" (fast, no database).
pytestmark = pytest.mark.unit


# --- Test data --------------------------------------------------------------
DATA_DIR = Path(__file__).parents[1] / "data"
SHP = DATA_DIR / "Test_Shape_A" / "Test_Shape_A_shp" / "Test_Shape_A.shp"  # the AOI box


# --- Helpers ----------------------------------------------------------------
def _valid_aoi() -> AreaOfInterest:
    """A normal AOI in BC Albers (metres) - what the operator expects."""
    gdf = gpd.read_file(SHP)
    return AOIBuilder().from_gdf(AOIRequest(aoi_id="test_aoi", name="Test AOI"), gdf)


def non_valid_aoi() -> AreaOfInterest:
    """A NON-projected (lat/long) AOI to check the operator rejects it.

    The AOI builder always converts to BC Albers, so we build a normal AOI and
    switch it back to lat/long (EPSG:4326) by hand.
    """
    aoi = _valid_aoi()
    aoi.gdf = aoi.gdf.to_crs(4326)
    return aoi


def _gdf(geoms, **columns) -> gpd.GeoDataFrame:
    """Wrap shapely polygons into a GeoDataFrame in BC Albers (EPSG:3005)."""
    return gpd.GeoDataFrame(dict(columns), geometry=geoms, crs="EPSG:3005")


class FakeAdapter(BaseSpatialAdapter):
    """A stand-in data source.

    Returns a GeoDataFrame we built in the test (or an empty one), and remembers
    the read_options it was handed so we can confirm the operator asked for the
    right search (touches vs within_distance).
    """

    def __init__(self, gdf: gpd.GeoDataFrame | None = None):
        self.gdf = gdf
        self.last_options = None

    def read(self, *, read_options=None, target_crs=None, **source_kwargs):
        self.last_options = read_options
        if self.gdf is None:
            return gpd.GeoDataFrame(geometry=[], crs="EPSG:3005")
        return self.gdf

    def _read_impl(self, *, read_options, **source_kwargs):
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:3005")

    def describe(self, **source_kwargs) -> DatasetInfo:
        raise NotImplementedError


# --- shared a boundary ------------------------------------------------------
def test_shares_full_edge_is_adjacent():
    """A box hugging the AOI's right edge shares that whole edge."""
    aoi = _valid_aoi()
    minx, miny, maxx, maxy = aoi.gdf.total_bounds
    poly = Polygon([(maxx, miny), (maxx + 500, miny), (maxx + 500, maxy), (maxx, maxy)])
    result = adjacency(aoi=aoi, adapter=FakeAdapter(_gdf([poly])), tolerance_m=0).parts[0].result
    assert result.is_adjacent is True
    assert result.measure_value == pytest.approx(maxy - miny)  # the AOI's height


def test_corner_touch_not_adjacent():
    """A box sitting on the AOI's top-right corner touches at a point only - no shared line."""
    aoi = _valid_aoi()
    minx, miny, maxx, maxy = aoi.gdf.total_bounds
    poly = Polygon([(maxx, maxy), (maxx + 500, maxy), (maxx + 500, maxy + 500), (maxx, maxy + 500)])
    result = adjacency(aoi=aoi, adapter=FakeAdapter(_gdf([poly])), tolerance_m=0).parts[0].result
    assert result.is_adjacent is False
    assert result.measure_value == 0.0


def test_sliver_gap_missed_at_zero_caught_with_tolerance():
    """A box 0.3 m off the edge: an exact touch misses it, a 0.5 m tolerance catches it."""
    aoi = _valid_aoi()
    minx, miny, maxx, maxy = aoi.gdf.total_bounds
    poly = Polygon([(maxx + 0.3, miny), (maxx + 500, miny), (maxx + 500, maxy), (maxx + 0.3, maxy)])
    exact = adjacency(aoi=aoi, adapter=FakeAdapter(_gdf([poly])), tolerance_m=0).parts[0].result
    tolerant = adjacency(aoi=aoi, adapter=FakeAdapter(_gdf([poly])), tolerance_m=0.5).parts[0].result
    assert exact.is_adjacent is False
    assert tolerant.is_adjacent is True


def test_empty_dataset_not_adjacent():
    """Nothing comes back from the source -> not adjacent."""
    result = adjacency(aoi=_valid_aoi(), adapter=FakeAdapter(), tolerance_m=0).parts[0].result
    assert result.is_adjacent is False
    assert result.feature_count == 0


def test_saved_features_match_the_result():
    """The features handed over for saving are the adjacent ones only.

    The source's search is a rough first pass: the corner-touch box comes back as a
    candidate but shares no border, so it must not end up in the saved file.
    """
    aoi = _valid_aoi()
    minx, miny, maxx, maxy = aoi.gdf.total_bounds
    edge = Polygon([(minx, maxy), (maxx, maxy), (maxx, maxy + 300), (minx, maxy + 300)])
    corner = Polygon([(maxx, maxy), (maxx + 300, maxy), (maxx + 300, maxy + 300), (maxx, maxy + 300)])
    gdf = _gdf([edge, corner], Id=[1, 2], Name=["edge", "corner"])

    outcome = adjacency(aoi=aoi, adapter=FakeAdapter(gdf), tolerance_m=0, keep_properties=["Name"])

    part = outcome.parts[0]
    saved = outcome.dataframes[part.aoi_part_id]
    assert part.result.feature_count == 1
    assert len(saved) == part.result.feature_count
    assert list(saved["Name"]) == ["edge"]


def test_multiple_adjacent_sorted_longest_first():
    """Two adjacent polygons come back longest-shared-border first, with IDs + columns."""
    aoi = _valid_aoi()
    minx, miny, maxx, maxy = aoi.gdf.total_bounds
    top = Polygon([(minx, maxy), (maxx, maxy), (maxx, maxy + 300), (minx, maxy + 300)])   # full top edge
    left = Polygon([(minx - 300, miny), (minx, miny), (minx, miny + 1000), (minx - 300, miny + 1000)])  # 1000 m of left edge
    gdf = _gdf([top, left], Id=[10, 11], Name=["top", "left"])

    result = adjacency(
        aoi=aoi, adapter=FakeAdapter(gdf), tolerance_m=0,
        feature_id_field="Id", keep_properties=["Name"],
    ).parts[0].result
    assert result.feature_count == 2
    measures = [f.measure for f in result.features]
    assert measures[0] > measures[1]                     # longest shared border first
    assert measures[0] == pytest.approx(maxx - minx)     # full top edge = AOI width
    assert measures[1] == pytest.approx(1000.0)          # 1000 m of the left edge
    assert result.measure_value == pytest.approx((maxx - minx) + 1000.0)  # total = sum
    assert [f.feature_id for f in result.features] == ["10", "11"]
    assert [f.properties["Name"] for f in result.features] == ["top", "left"]


# --- bad input / wrong CRS is rejected --------------------------------------
def test_negative_tolerance_raises():
    with pytest.raises(ValueError):
        adjacency(aoi=_valid_aoi(), adapter=FakeAdapter(), tolerance_m=-1)


def test_non_valid_aoi_rejected():
    """A lat/long AOI (degrees) is refused - shared length must be in metres."""
    with pytest.raises(ValueError):
        adjacency(aoi=non_valid_aoi(), adapter=FakeAdapter(), tolerance_m=0)


# --- the operator asks the data source for the right search -----------------
def test_exact_match_asks_for_touches_search():
    adapter = FakeAdapter()
    adjacency(aoi=_valid_aoi(), adapter=adapter, tolerance_m=0)
    assert adapter.last_options.spatial_filter.predicate == "touches"


def test_tolerant_match_asks_for_within_distance_search():
    adapter = FakeAdapter()
    adjacency(aoi=_valid_aoi(), adapter=adapter, tolerance_m=5)
    sf = adapter.last_options.spatial_filter
    assert sf.predicate == "within_distance"
    assert sf.distance == 5


# --- an AOI of two parts: only each part's outer edge counts ----------------
def _two_block_aoi() -> AreaOfInterest:
    """The AOI box cut into block A (west) and block B (east), grouped by a
    "block" field, so it has two parts. The two blocks share the middle edge."""
    minx, miny, maxx, maxy = _valid_aoi().gdf.total_bounds
    mid = (minx + maxx) / 2
    block_a = Polygon([(minx, miny), (mid, miny), (mid, maxy), (minx, maxy)])
    block_b = Polygon([(mid, miny), (maxx, miny), (maxx, maxy), (mid, maxy)])
    gdf = gpd.GeoDataFrame({"block": ["A", "B"]}, geometry=[block_a, block_b], crs="EPSG:3005")
    request = AOIRequest(
        aoi_id="test_aoi", name="Two blocks", dissolve_mode="by_fields", dissolve_fields=("block",)
    )
    return AOIBuilder().from_gdf(request, gdf)


def test_edge_between_two_parts_does_not_count():
    """A polygon inside block B, along the A|B edge, is adjacent to neither block:
    that edge is inside the AOI. A polygon across the top touches both blocks'
    outer edge, and each block reports the length it shares."""
    aoi = _two_block_aoi()
    minx, miny, maxx, maxy = aoi.gdf.total_bounds
    mid = (minx + maxx) / 2
    inside_b = Polygon([(mid, miny + 100), (mid + 300, miny + 100), (mid + 300, maxy - 100), (mid, maxy - 100)])
    across_top = Polygon([(mid - 400, maxy), (mid + 600, maxy), (mid + 600, maxy + 200), (mid - 400, maxy + 200)])
    gdf = _gdf([inside_b, across_top], Name=["inside_b", "across_top"])

    outcome = adjacency(aoi=aoi, adapter=FakeAdapter(gdf), tolerance_m=0, keep_properties=["Name"])

    block_a, block_b = outcome.parts
    assert [block_a.part_attributes, block_b.part_attributes] == [{"block": "A"}, {"block": "B"}]
    assert [f.properties["Name"] for f in block_a.result.features] == ["across_top"]
    assert [f.properties["Name"] for f in block_b.result.features] == ["across_top"]
    assert block_a.result.measure_value == pytest.approx(400.0)   # 400 m along A's top edge
    assert block_b.result.measure_value == pytest.approx(600.0)   # 600 m along B's top edge
