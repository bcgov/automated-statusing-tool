"""Proximity unit tests using generated geometry and controlled adapter responses.

Place this module at ast_engine/tests/unit/operator/test_proximity.py.
It reuses the existing AOIStub, geometry helpers and InMemorySpatialAdapter.
No AOIBuilder, FileSpatialAdapter, shapefiles or dataset paths are required.

The usual AOI is the helper's 2,000 m by 1,500 m rectangle in EPSG:3005.
Points are placed exactly 3 m, 10 m and 2,000 m east of its right boundary,
at the vertical midpoint. Their distances are exact geometric expectations;
the old shapefile's 1,999.25 m expectation is intentionally replaced by 2,000 m.

The adapter returns the supplied rows unchanged, without filtering, sorting
or limiting k. The real operators must perform those operations themselves.
Unsorted candidates therefore exercise both distance calculation and selection.

Regression cases for NaN/pd.NA IDs and property iterators intentionally remain
ordinary assertions. Against the supplied implementation, two null-ID cases
and the iterator case for each operator should fail. They require the same
fixes discussed for overlay: recognise pandas nulls in _extract_feature_id,
and convert keep_properties to a reusable tuple in BOTH public operators
before constructing the default read options.
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point

from ast_engine.core.data_adapters.base import ReadOptions, SpatialFilter
from ast_engine.core.operator.proximity import (
    _default_read_options,
    _extract_feature_id,
    nearest,
    within_distance,
)
from ast_engine.core.results import ProximityResult
from ast_engine.tests.helpers.aoi_cases import (
    AOIStub,
    geographic_operator_aoi,
    projected_operator_aoi,
)
from ast_engine.tests.helpers.aoi_geometry import aoi_gdf, rect
from ast_engine.tests.helpers.spatial_adapters import InMemorySpatialAdapter


pytestmark = pytest.mark.unit


# Shared scenarios run against both public operators. These argument mappings
# are only unpacked with **operator_kwargs; tests never modify them.
_OPERATORS = (
    pytest.param(
        within_distance, {"distance_m": 12.0}, id="within-distance"
    ),
    pytest.param(nearest, {"k": 2}, id="nearest"),
)


def _points_at_distances(aoi, distances_m, **columns) -> gpd.GeoDataFrame:
    """Create fresh points at nonnegative gaps east of the rectangular AOI."""
    _, miny, maxx, maxy = aoi.gdf.total_bounds
    y = (miny + maxy) / 2
    return aoi_gdf(
        [Point(maxx + distance, y) for distance in distances_m],
        crs=aoi.gdf.crs,
        **columns,
    )


def _proximity_features(aoi) -> gpd.GeoDataFrame:
    """Return 10 m, 2,000 m and 3 m candidates, deliberately out of order."""
    return _points_at_distances(
        aoi,
        [10.0, 2_000.0, 3.0],
        Id=[20, 30, 10],
        Name=["ten", "far", "three"],
        Colour=["Blue", "Red", "Green"],
    )


@pytest.mark.parametrize(
    ("point_distance_m", "radius_m"),
    [
        pytest.param(3.0, 12.0, id="3-metres"),
        pytest.param(10.0, 12.0, id="10-metres"),
        pytest.param(2_000.0, 3_000.0, id="2000-metres"),
    ],
)
def test_within_distance_measures_known_distances(point_distance_m, radius_m):
    """Measure the gap to the AOI boundary, without shapefile rounding."""
    aoi = projected_operator_aoi()
    source = _points_at_distances(aoi, [point_distance_m])

    result = within_distance(
        aoi=aoi,
        adapter=InMemorySpatialAdapter(source),
        distance_m=radius_m,
    )

    assert isinstance(result, ProximityResult)
    assert result.feature_count == 1
    assert result.measure_value == pytest.approx(point_distance_m)
    assert [feature.measure for feature in result.features] == pytest.approx(
        [point_distance_m]
    )


def test_within_distance_filters_and_sorts_results():
    """Keep 3 m and 10 m, drop 2,000 m, and preserve attributes after sorting."""
    aoi = projected_operator_aoi()

    result = within_distance(
        aoi=aoi,
        adapter=InMemorySpatialAdapter(_proximity_features(aoi)),
        distance_m=12.0,
        feature_id_field="Id",
        keep_properties=["Name", "Colour"],
    )

    assert result.feature_count == 2
    assert result.measure_value == pytest.approx(3.0)
    assert [feature.measure for feature in result.features] == pytest.approx(
        [3.0, 10.0]
    )
    assert [feature.feature_id for feature in result.features] == ["10", "20"]
    assert [feature.properties for feature in result.features] == [
        {"Name": "three", "Colour": "Green"},
        {"Name": "ten", "Colour": "Blue"},
    ]


def test_within_distance_includes_exact_radius():
    """The radius is inclusive: keep 11.75 m and 12 m, exclude 12.25 m."""
    aoi = projected_operator_aoi()
    source = _points_at_distances(
        aoi,
        [12.25, 12.0, 11.75],
        Id=[13, 12, 11],
    )

    result = within_distance(
        aoi=aoi,
        adapter=InMemorySpatialAdapter(source),
        distance_m=12.0,
        feature_id_field="Id",
    )

    assert result.feature_count == 2
    assert result.measure_value == pytest.approx(11.75)
    assert [feature.measure for feature in result.features] == pytest.approx(
        [11.75, 12.0]
    )
    assert [feature.feature_id for feature in result.features] == ["11", "12"]


@pytest.mark.parametrize(
    ("k", "expected_ids", "expected_distances"),
    [
        pytest.param(1, ("10",), (3.0,), id="one-nearest"),
        pytest.param(2, ("10", "20"), (3.0, 10.0), id="two-nearest"),
        pytest.param(
            5,
            ("10", "20", "30"),
            (3.0, 10.0, 2_000.0),
            id="k-exceeds-candidate-count",
        ),
    ],
)
def test_nearest_sorts_before_limiting_k(k, expected_ids, expected_distances):
    """Choose the closest k from unsorted input, or all if fewer than k exist."""
    aoi = projected_operator_aoi()

    result = nearest(
        aoi=aoi,
        adapter=InMemorySpatialAdapter(_proximity_features(aoi)),
        k=k,
        feature_id_field="Id",
    )

    assert isinstance(result, ProximityResult)
    assert result.feature_count == len(expected_distances)
    assert result.measure_value == pytest.approx(3.0)
    assert [feature.measure for feature in result.features] == pytest.approx(
        list(expected_distances)
    )
    assert [feature.feature_id for feature in result.features] == list(
        expected_ids
    )


def test_nearest_defaults_to_one_feature():
    """Omitting k exercises the real public default, without a factory value."""
    aoi = projected_operator_aoi()

    result = nearest(
        aoi=aoi,
        adapter=InMemorySpatialAdapter(_proximity_features(aoi)),
        feature_id_field="Id",
    )

    assert result.feature_count == 1
    assert result.measure_value == pytest.approx(3.0)
    assert [feature.feature_id for feature in result.features] == ["10"]
    assert result.features[0].properties == {}


@pytest.mark.parametrize(
    ("max_distance_m", "expected_distances"),
    [
        pytest.param(5.0, (3.0,), id="cap-removes-second-nearest"),
        pytest.param(10.0, (3.0, 10.0), id="cap-is-inclusive"),
    ],
)
def test_nearest_applies_max_distance_cap(max_distance_m, expected_distances):
    """The optional cap is inclusive and may return fewer than k features."""
    aoi = projected_operator_aoi()

    result = nearest(
        aoi=aoi,
        adapter=InMemorySpatialAdapter(_proximity_features(aoi)),
        k=2,
        max_distance_m=max_distance_m,
    )

    assert result.feature_count == len(expected_distances)
    assert result.measure_value == pytest.approx(3.0)
    assert [feature.measure for feature in result.features] == pytest.approx(
        list(expected_distances)
    )


@pytest.mark.parametrize(
    ("operator", "operator_kwargs"),
    [
        pytest.param(
            within_distance,
            {"distance_m": 0.125},
            id="within-positive-radius",
        ),
        pytest.param(
            nearest,
            {"k": 3, "max_distance_m": 0.0},
            id="nearest-zero-cap",
        ),
    ],
)
def test_intersecting_points_report_zero_distance(operator, operator_kwargs):
    """Interior and boundary points have distance zero; a 0.25 m gap fails."""
    aoi = projected_operator_aoi()
    minx, miny, maxx, maxy = aoi.gdf.total_bounds
    y = (miny + maxy) / 2
    source = aoi_gdf(
        [
            Point(maxx + 0.25, y),
            Point(maxx, y),
            Point((minx + maxx) / 2, y),
        ],
        crs=aoi.gdf.crs,
        Id=["outside", "boundary", "inside"],
    )

    result = operator(
        aoi=aoi,
        adapter=InMemorySpatialAdapter(source),
        feature_id_field="Id",
        **operator_kwargs,
    )

    assert result.feature_count == 2
    assert result.measure_value == 0.0
    assert [feature.measure for feature in result.features] == [0.0, 0.0]
    # Equal distances have no specified tie order.
    assert {feature.feature_id for feature in result.features} == {
        "boundary",
        "inside",
    }


def test_within_distance_rejects_zero_radius():
    aoi = projected_operator_aoi()
    adapter = InMemorySpatialAdapter()

    with pytest.raises(ValueError):
        within_distance(
            aoi=aoi,
            adapter=adapter,
            distance_m=0.0,
        )

    # Invalid input should be rejected before requesting any data.
    assert adapter.last_source_kwargs is None


@pytest.mark.parametrize(("operator", "operator_kwargs"), _OPERATORS)
def test_empty_adapter_returns_zero_result(operator, operator_kwargs):
    """Both operators return an empty ProximityResult for an empty source."""
    result = operator(
        aoi=projected_operator_aoi(),
        adapter=InMemorySpatialAdapter(),
        **operator_kwargs,
    )

    assert isinstance(result, ProximityResult)
    assert result.feature_count == 0
    assert result.measure_value == 0.0
    assert result.features == []


@pytest.mark.parametrize(
    ("operator", "operator_kwargs"),
    [
        pytest.param(
            within_distance, {"distance_m": 5.0}, id="within-distance"
        ),
        pytest.param(
            nearest, {"k": 2, "max_distance_m": 5.0}, id="nearest"
        ),
    ],
)
def test_all_candidates_outside_limit_return_zero_result(operator, operator_kwargs):
    """Nonempty input can become empty after the operator applies its limit."""
    aoi = projected_operator_aoi()
    source = _points_at_distances(aoi, [2_000.0, 10.0])

    result = operator(
        aoi=aoi,
        adapter=InMemorySpatialAdapter(source),
        **operator_kwargs,
    )

    assert isinstance(result, ProximityResult)
    assert result.feature_count == 0
    assert result.measure_value == 0.0
    assert result.features == []


@pytest.mark.parametrize(("operator", "operator_kwargs"), _OPERATORS)
def test_missing_id_column_uses_source_index_labels(operator, operator_kwargs):
    """Fallback IDs and kept colours remain attached to their sorted rows."""
    aoi = projected_operator_aoi()
    source = _proximity_features(aoi).drop(columns=["Id"])
    source.index = [101, 202, 303]  # 10 m, 2,000 m, 3 m

    result = operator(
        aoi=aoi,
        adapter=InMemorySpatialAdapter(source),
        feature_id_field="NOT_REAL",
        keep_properties=["Colour"],
        **operator_kwargs,
    )

    assert result.feature_count == 2
    assert [feature.feature_id for feature in result.features] == ["303", "101"]
    assert [feature.properties for feature in result.features] == [
        {"Colour": "Green"},
        {"Colour": "Blue"},
    ]


@pytest.mark.parametrize(
    "null_id",
    [
        pytest.param(None, id="none"),
        pytest.param(float("nan"), id="nan"),
        pytest.param(pd.NA, id="pandas-na"),
    ],
)
def test_null_feature_id_falls_back_to_index_label(null_id):
    """An existing but null ID attribute falls back to the source index label."""
    row = pd.Series({"Id": null_id}, dtype=object)

    feature_id = _extract_feature_id(row, idx=73, feature_id_field="Id")

    assert feature_id == "73"


def test_zero_feature_id_is_preserved():
    """An ID of zero is valid and must not trigger the missing-ID fallback."""
    row = pd.Series({"Id": 0}, dtype=object)

    feature_id = _extract_feature_id(row, idx=73, feature_id_field="Id")

    assert feature_id == "0"


@pytest.mark.parametrize(("operator", "operator_kwargs"), _OPERATORS)
@pytest.mark.parametrize(
    "make_keep_properties",
    [
        pytest.param(list, id="list"),
        pytest.param(iter, id="iterator"),
    ],
)
def test_keep_properties_accepts_reusable_and_one_shot_iterables(
    operator,
    operator_kwargs,
    make_keep_properties,
):
    """Both entry points must retain names for read options and result records."""
    aoi = projected_operator_aoi()
    adapter = InMemorySpatialAdapter(_proximity_features(aoi))

    result = operator(
        aoi=aoi,
        adapter=adapter,
        feature_id_field="Id",
        keep_properties=make_keep_properties(["Name"]),
        **operator_kwargs,
    )

    assert adapter.last_options is not None
    assert set(adapter.last_options.keep_columns) == {"Id", "Name"}
    assert result.feature_count == 2
    assert [feature.properties for feature in result.features] == [
        {"Name": "three"},
        {"Name": "ten"},
    ]


def test_default_read_options_preserves_filter_and_columns():
    """Build the request using the given filter, attributes and where clause."""
    spatial_filter = SpatialFilter(
        aoi=projected_operator_aoi().gdf,
        predicate="within_distance",
        distance=12.0,
    )
    where = "STATUS = 'ACTIVE'"

    options = _default_read_options(
        spatial_filter,
        "Id",
        ["Colour"],
        where=where,
    )

    assert options.spatial_filter is spatial_filter
    assert set(options.keep_columns) == {"Id", "Colour"}
    assert options.where == where


@pytest.mark.parametrize(("operator", "operator_kwargs"), _OPERATORS)
def test_operator_forwards_default_request_and_source_arguments(
    operator,
    operator_kwargs,
):
    """The operator requests its search, AOI, columns, CRS and dataset source."""
    aoi = projected_operator_aoi()
    adapter = InMemorySpatialAdapter()
    where = "STATUS = 'ACTIVE'"

    operator(
        aoi=aoi,
        adapter=adapter,
        feature_id_field="Id",
        keep_properties=["Colour"],
        where=where,
        table="TEST_FEATURES",  # A recorded argument, with no database access.
        **operator_kwargs,
    )

    options = adapter.last_options
    assert options is not None
    spatial_filter = options.spatial_filter
    assert spatial_filter is not None
    assert spatial_filter.aoi.equals(aoi.gdf)
    assert spatial_filter.aoi.crs == aoi.gdf.crs
    if operator is within_distance:
        assert spatial_filter.predicate == "within_distance"
        assert spatial_filter.distance == 12.0
    else:
        assert spatial_filter.predicate == "nearest"
        assert spatial_filter.k == 2
    assert set(options.keep_columns) == {"Id", "Colour"}
    assert options.where == where
    assert adapter.last_target_crs == str(aoi.gdf.crs)
    assert adapter.last_source_kwargs == {"table": "TEST_FEATURES"}


@pytest.mark.parametrize(("operator", "operator_kwargs"), _OPERATORS)
def test_explicit_read_options_are_used_unchanged(operator, operator_kwargs):
    """An explicit request takes precedence over the operator's defaults."""
    aoi = projected_operator_aoi()
    adapter = InMemorySpatialAdapter()
    options = ReadOptions(
        spatial_filter=SpatialFilter(aoi=aoi.gdf, predicate="touches"),
        where="STATUS = 'CUSTOM'",
        keep_columns={"Colour"},
    )

    operator(
        aoi=aoi,
        adapter=adapter,
        read_options=options,
        feature_id_field="Id",
        keep_properties=["Colour"],
        where="STATUS = 'DEFAULT'",
        **operator_kwargs,
    )

    assert adapter.last_options is options
    assert options.spatial_filter is not None
    assert options.spatial_filter.predicate == "touches"
    assert options.where == "STATUS = 'CUSTOM'"
    assert set(options.keep_columns) == {"Colour"}


@pytest.mark.parametrize(
    ("operator", "operator_kwargs", "message"),
    [
        pytest.param(
            within_distance,
            {"distance_m": -1},
            "distance_m must be positive",
            id="negative-radius",
        ),
        pytest.param(
            within_distance,
            {"distance_m": 0.0},
            "distance_m must be positive",
            id="zero-radius",
        ),
        pytest.param(
            nearest,
            {"k": 0},
            "k must be at least 1",
            id="zero-k",
        ),
        pytest.param(
            nearest,
            {"k": -1},
            "k must be at least 1",
            id="negative-k",
        ),
        pytest.param(
            nearest,
            {"k": 1, "max_distance_m": -1},
            "max_distance_m must be non-negative",
            id="negative-cap",
        ),
    ],
)
def test_invalid_arguments_rejected_before_adapter_read(
    operator,
    operator_kwargs,
    message,
):
    adapter = InMemorySpatialAdapter()

    with pytest.raises(ValueError, match=message):
        operator(
            aoi=projected_operator_aoi(),
            adapter=adapter,
            **operator_kwargs,
        )

    # The helper records a dictionary, even an empty one, whenever read runs.
    assert adapter.last_source_kwargs is None


@pytest.mark.parametrize(("operator", "operator_kwargs"), _OPERATORS)
def test_geographic_aoi_rejected_before_adapter_read(operator, operator_kwargs):
    adapter = InMemorySpatialAdapter()

    with pytest.raises(ValueError, match="projected CRS"):
        operator(
            aoi=geographic_operator_aoi(),
            adapter=adapter,
            **operator_kwargs,
        )

    assert adapter.last_source_kwargs is None


@pytest.mark.parametrize(("operator", "operator_kwargs"), _OPERATORS)
def test_missing_crs_rejected_before_adapter_read(operator, operator_kwargs):
    projected = projected_operator_aoi()
    aoi = AOIStub(
        gdf=aoi_gdf(list(projected.gdf.geometry), crs=None),
        aoi_id="missing_crs",
    )
    adapter = InMemorySpatialAdapter()

    with pytest.raises(ValueError, match="projected CRS"):
        operator(aoi=aoi, adapter=adapter, **operator_kwargs)

    assert adapter.last_source_kwargs is None


@pytest.mark.parametrize(("operator", "operator_kwargs"), _OPERATORS)
def test_distance_uses_all_aoi_parts_and_excludes_the_gap(operator, operator_kwargs):
    """A point in the second AOI part is 0 m away; a point in the gap is 5 m."""
    x, y = 1_000_000, 1_000_000
    aoi = AOIStub(
        gdf=aoi_gdf(
            [
                rect(x, y, x + 100, y + 100),
                rect(x + 110, y, x + 210, y + 100),
            ]
        )
    )
    source = aoi_gdf(
        [Point(x + 105, y + 50), Point(x + 160, y + 50)],
        crs=aoi.gdf.crs,
        Id=["gap", "second-part"],
    )

    result = operator(
        aoi=aoi,
        adapter=InMemorySpatialAdapter(source),
        feature_id_field="Id",
        **operator_kwargs,
    )

    assert result.feature_count == 2
    assert result.measure_value == 0.0
    assert [feature.measure for feature in result.features] == pytest.approx(
        [0.0, 5.0]
    )
    assert [feature.feature_id for feature in result.features] == [
        "second-part",
        "gap",
    ]
