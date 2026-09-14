"""
Unit tests for the adjacency operator.

PURPOSE
-------
Verify adjacency using small polygons with known shared boundary lengths.

The operator measures the boundary length shared between dataset features
and the AOI, and reports per-feature lengths and their total.

Tests use controlled Shapely geometries and an in-memory data source without
reading shapefiles. The AOI is a rectangle in BC Albers (EPSG:3005).

COVERAGE
--------
- Identify polygons sharing a full AOI edge and measure the shared length.
- Exclude corner-only contacts, which have no shared line length.
- Exclude polygons separated by a gap when using exact adjacency.
- Include polygons within the specified gap tolerance.
- Return an empty result for an empty dataset.
- Sort adjacent features from longest to shortest shared boundary.
- Preserve feature IDs and requested properties after sorting.
- Report the total shared boundary length.
- Reject negative tolerance values and geographic AOIs.
- Request the appropriate source predicate: touches for exact adjacency
  or within_distance when using a tolerance.

HOW TO EXTEND
-------------
1. Add a descriptively named test for each new behaviour or edge case.
2. Use small polygons with independently calculable shared-edge lengths.
3. Create fresh AOI stubs, GeoDataFrames, and in-memory adapters for each
   test; avoid depending on the production AOI builder.
4. Keep specialised geometry close to the test that uses it. Reuse shared
   helpers when multiple tests need the same scenario.
5. Check per-feature lengths and totals together, using pytest.approx()
   for floating-point comparisons.
6. Verify that IDs and properties remain associated with the correct
   features after sorting.
7. Check source requests through adapter recordings. Keep actual file
   access and source-adapter integration tests separate.
"""

import pytest
from shapely.geometry import Polygon

from ast_engine.tests.helpers.aoi_cases import (
    geographic_operator_aoi,
    projected_operator_aoi,
)
from ast_engine.core.operator.adjacent import adjacency
from ast_engine.tests.helpers.aoi_geometry import rect, aoi_gdf
from ast_engine.tests.helpers.spatial_adapters import InMemorySpatialAdapter


pytestmark = pytest.mark.unit


# # --- shared a boundary ------------------------------------------------------
def test_shares_full_edge_is_adjacent():
    """A box sharing the AOI's right edge is adjacent, and the shared length is correct."""

    aoi = projected_operator_aoi()

    minx, miny, maxx, maxy = aoi.gdf.total_bounds
    polygon = Polygon(
        [
            (maxx, miny),
            (maxx + 500, miny),
            (maxx + 500, maxy),
            (maxx, maxy),
        ]
    )

    result = adjacency(
        aoi=aoi,
        adapter=InMemorySpatialAdapter(aoi_gdf([polygon])),
        tolerance_m=0,
    )

    assert result.is_adjacent is True
    assert result.measure_value == pytest.approx(maxy - miny)


def test_corner_touch_not_adjacent():
    """A box sitting on the AOI's top-right corner touches at a point only - no shared line."""

    aoi = projected_operator_aoi()

    minx, miny, maxx, maxy = aoi.gdf.total_bounds
    poly = Polygon(
        [(maxx, maxy),
         (maxx + 500, maxy),
         (maxx + 500, maxy + 500),
         (maxx, maxy + 500)]
    )

    result = adjacency(
        aoi=aoi,
        adapter=InMemorySpatialAdapter(aoi_gdf([poly])),
        tolerance_m=0
    )

    assert result.is_adjacent is False
    assert result.measure_value == 0.0


@pytest.mark.parametrize(
    ("gap_m", "expected_adjacent"),
    [
        pytest.param(0.25, True, id="gap-below-tolerance"),
        pytest.param(0.75, False, id="gap-above-tolerance"),
    ],
)
def test_positive_tolerance_accepts_only_nearby_polygons(
    gap_m,
    expected_adjacent,
):
    """A 0.5 m tolerance accepts 0.25 m and rejects 0.75 m."""

    aoi = projected_operator_aoi()
    _, miny, maxx, _ = aoi.gdf.total_bounds

    source = aoi_gdf(
        [
            rect(
                maxx + gap_m,
                miny + 100,
                maxx + gap_m + 20,
                miny + 200,
            )
        ],
        crs=aoi.gdf.crs,
        Id=["candidate"],
    )

    result = adjacency(
        aoi=aoi,
        adapter=InMemorySpatialAdapter(source),
        tolerance_m=0.5,
        feature_id_field="Id",
    )

    assert result.is_adjacent is expected_adjacent
    assert result.feature_count == (1 if expected_adjacent else 0)

    if expected_adjacent:
        assert [f.feature_id for f in result.features] == ["candidate"]
        assert result.features[0].measure > 0
        assert result.measure_value == pytest.approx(
            result.features[0].measure
        )
    else:
        assert result.features == []
        assert result.measure_value == 0.0


def test_empty_dataset_not_adjacent():
    """Nothing comes back from the source -> not adjacent."""

    aoi = projected_operator_aoi()

    result = adjacency(aoi=aoi, adapter=InMemorySpatialAdapter(), tolerance_m=0)
    assert result.is_adjacent is False
    assert result.feature_count == 0


def test_multiple_adjacent_sorted_longest_first():
    """Two adjacent polygons come back longest-shared-border first, with IDs + columns."""

    aoi = projected_operator_aoi()

    minx, miny, maxx, maxy = aoi.gdf.total_bounds
    top = Polygon([(minx, maxy), (maxx, maxy), (maxx, maxy + 300), (minx, maxy + 300)])   # full top edge
    left = Polygon([(minx - 300, miny), (minx, miny), (minx, miny + 1000), (minx - 300, miny + 1000)])  # 1000 m of left edge
    gdf = aoi_gdf([left, top], Id=[11, 10], Name=["left", "top"])

    result = adjacency(
        aoi=aoi, adapter=InMemorySpatialAdapter(gdf), tolerance_m=0,
        feature_id_field="Id", keep_properties=["Name"],
    )
    assert result.feature_count == 2
    measures = [f.measure for f in result.features]
    assert measures[0] > measures[1]                     # longest shared border first
    assert measures[0] == pytest.approx(maxx - minx)     # full top edge = AOI width
    assert measures[1] == pytest.approx(1000.0)          # 1000 m of the left edge
    assert result.measure_value == pytest.approx((maxx - minx) + 1000.0)  # total = sum
    assert [f.feature_id for f in result.features] == ["10", "11"]
    assert [f.properties["Name"] for f in result.features] == ["top", "left"]
    assert [f.measure for f in result.features] == pytest.approx(
        [2000.0, 1000.0]
    )


def test_negative_tolerance_raises():
    """A negative tolerance is rejected with a ValueError."""

    aoi = projected_operator_aoi()
    
    with pytest.raises(ValueError):
        adjacency(aoi=aoi, adapter=InMemorySpatialAdapter(), tolerance_m=-1)


def test_non_valid_aoi_rejected():
    """A lat/long AOI (degrees) is refused - shared length must be in metres."""

    aoi = geographic_operator_aoi()

    with pytest.raises(ValueError):
        adjacency(aoi=aoi, adapter=InMemorySpatialAdapter(), tolerance_m=0)


def test_exact_match_asks_for_touches_search():
    """A zero-tolerance adjacency search asks the source for a "touches" search."""
    
    aoi = projected_operator_aoi()

    adapter = InMemorySpatialAdapter()
    adjacency(aoi=aoi, adapter=adapter, tolerance_m=0)

    assert adapter.last_options.spatial_filter.predicate == "touches"


def test_tolerant_match_asks_for_within_distance_search():
    """A tolerant adjacency search asks the source for a "within_distance" search."""

    aoi = projected_operator_aoi()

    tolerance = 5

    adapter = InMemorySpatialAdapter()
    adjacency(aoi=aoi, adapter=adapter, tolerance_m=tolerance)
    sf = adapter.last_options.spatial_filter

    assert sf.predicate == "within_distance"
    assert sf.distance == tolerance
