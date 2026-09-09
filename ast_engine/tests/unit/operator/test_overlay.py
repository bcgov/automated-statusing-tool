"""Overlay unit tests using generated geometry and controlled adapter responses.

Place this module at ast_engine/tests/unit/operator/test_overlay.py.
It reuses the project's existing AOI, geometry, and adapter test helpers.
No AOIBuilder, FileSpatialAdapter, shapefiles, or dataset paths are used.

The AOI helper supplies a 2,000 m by 1,500 m rectangle in EPSG:3005.
Polygon intersections have areas of 20,000 and 10,000 square metres (3 ha
in total). Line intersections have lengths of 200 and 100 metres. One
interior point and one boundary point qualify; the outside point does not.

InMemorySpatialAdapter returns its configured rows unchanged. Tests that
supply outside features exercise the real intersection() function's
removal of empty or zero-measure intersections. The response stub does
not simulate the requested spatial or attribute filters.

The result-type override cases also check counts and measurements when
overrides differ from the source geometry type.

The null-ID (NaN/pd.NA) and keep-properties iterator cases expose defects
in the supplied operator. They deliberately remain ordinary assertions,
so those cases should fail until the production implementation is fixed.
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import LineString, Point

from ast_engine.core.data_adapters.base import ReadOptions, SpatialFilter
from ast_engine.core.operator.overlay import (
    _default_read_options,
    _extract_feature_id,
    _infer_geom_kind,
    intersection,
)
from ast_engine.core.results import (
    LineOverlayResult,
    PointOverlayResult,
    PolyOverlayResult,
)
from ast_engine.tests.helpers.aoi_cases import (
    AOIStub,
    geographic_operator_aoi,
    projected_operator_aoi,
)
from ast_engine.tests.helpers.aoi_geometry import aoi_gdf, rect
from ast_engine.tests.helpers.spatial_adapters import InMemorySpatialAdapter


pytestmark = pytest.mark.unit


# Repeated scenarios stay local to this test module. Every call creates
# fresh geometries and a fresh GeoDataFrame; IDs are supplied explicitly.
def _polygon_features(aoi) -> gpd.GeoDataFrame:
    """Partial, outside, inside: deliberately not sorted by overlap area."""
    minx, miny, maxx, _ = aoi.gdf.total_bounds

    # Full rectangle: 200 m wide by 100 m high, entirely inside the AOI.
    inside = rect(minx + 100, miny + 100, minx + 300, miny + 200)

    # Half of this 200 m by 100 m rectangle lies inside the AOI.
    partial = rect(maxx - 100, miny + 100, maxx + 100, miny + 200)

    outside = rect(maxx + 300, miny + 100, maxx + 400, miny + 200)

    return aoi_gdf(
        [partial, outside, inside],
        crs=aoi.gdf.crs,
        Id=[22, 33, 11],
        Name=["partial", "outside", "inside"],
    )


def _line_features(aoi) -> gpd.GeoDataFrame:
    """Crossing, outside, inside: overlaps are 100 m, 0 m, and 200 m."""
    minx, miny, maxx, _ = aoi.gdf.total_bounds

    inside = LineString(
        [(minx + 100, miny + 400), (minx + 300, miny + 400)]
    )
    crossing = LineString(
        [(maxx - 100, miny + 500), (maxx + 100, miny + 500)]
    )
    outside = LineString(
        [(maxx + 300, miny + 600), (maxx + 400, miny + 600)]
    )

    return aoi_gdf(
        [crossing, outside, inside],
        crs=aoi.gdf.crs,
        Id=[22, 33, 11],
        Name=["crossing", "outside", "inside"],
    )


def _point_features(aoi) -> gpd.GeoDataFrame:
    """One outside point, one interior point, and one boundary point."""
    minx, miny, maxx, maxy = aoi.gdf.total_bounds

    inside = Point((minx + maxx) / 2, (miny + maxy) / 2)
    boundary = Point(maxx, maxy)
    outside = Point(maxx + 100, maxy + 100)

    return aoi_gdf(
        [outside, inside, boundary],
        crs=aoi.gdf.crs,
        Id=[30, 10, 20],
        Name=["Outside", "First", "Second"],
    )


def test_polygon_overlap_exact_values():
    """Two qualifying polygons contribute 20,000 + 10,000 = 30,000 m2."""
    aoi = projected_operator_aoi()

    result = intersection(
        aoi=aoi,
        adapter=InMemorySpatialAdapter(_polygon_features(aoi)),
        keep_properties=["Name"],
    )

    assert result.feature_count == 2
    assert len(result.features) == 2
    assert result.total_area == pytest.approx(30_000.0)
    measures = {
        feature.properties["Name"]: feature.measure
        for feature in result.features
    }
    assert measures == pytest.approx({"inside": 20_000.0, "partial": 10_000.0})


def test_line_overlap_exact_values():
    """A 200 m interior line and 100 m of a crossing line total 300 m."""
    aoi = projected_operator_aoi()

    result = intersection(
        aoi=aoi,
        adapter=InMemorySpatialAdapter(_line_features(aoi)),
        keep_properties=["Name"],
    )

    assert result.feature_count == 2
    assert len(result.features) == 2
    assert result.total_length == pytest.approx(300.0)
    assert [feature.measure for feature in result.features] == pytest.approx(
        [200.0, 100.0]
    )
    assert [feature.properties["Name"] for feature in result.features] == [
        "inside",
        "crossing",
    ]


def test_point_overlay_count():
    """Interior and boundary points qualify, with no length/area measure."""
    aoi = projected_operator_aoi()

    result = intersection(
        aoi=aoi,
        adapter=InMemorySpatialAdapter(_point_features(aoi)),
        keep_properties=["Name"],
    )

    assert result.feature_count == 2
    assert result.measure_value == 2
    assert len(result.features) == 2
    assert {feature.properties["Name"] for feature in result.features} == {
        "First",
        "Second",
    }
    assert all(feature.measure is None for feature in result.features)


def test_sorted_descending_by_overlap():
    """Unsorted polygon input is returned in descending overlap-area order."""
    aoi = projected_operator_aoi()

    result = intersection(
        aoi=aoi,
        adapter=InMemorySpatialAdapter(_polygon_features(aoi)),
        feature_id_field="Id",
    )

    assert result.feature_count == 2
    assert [feature.measure for feature in result.features] == pytest.approx(
        [20_000.0, 10_000.0]
    )
    assert [feature.feature_id for feature in result.features] == ["11", "22"]


def test_zero_overlap_removed():
    """The outside candidate is removed while positive overlaps remain."""
    aoi = projected_operator_aoi()

    result = intersection(
        aoi=aoi,
        adapter=InMemorySpatialAdapter(_polygon_features(aoi)),
        keep_properties=["Name"],
    )

    assert result.feature_count == 2
    assert len(result.features) == 2
    assert {feature.properties["Name"] for feature in result.features} == {
        "inside",
        "partial",
    }
    assert all(feature.measure > 0 for feature in result.features)


def test_properties_preserved():
    """Names stay associated with the correct explicit IDs after sorting."""
    aoi = projected_operator_aoi()

    result = intersection(
        aoi=aoi,
        adapter=InMemorySpatialAdapter(_polygon_features(aoi)),
        feature_id_field="Id",
        keep_properties=["Name"],
    )

    assert result.feature_count == 2
    assert len(result.features) == 2
    assert {
        feature.feature_id: feature.properties["Name"]
        for feature in result.features
    } == {"11": "inside", "22": "partial"}


def test_feature_id_fallback():
    """Fallback IDs retain source index labels through filtering and sorting."""
    aoi = projected_operator_aoi()
    source = _polygon_features(aoi).drop(columns=["Id"])
    source.index = [101, 202, 303]  # partial, outside, inside

    result = intersection(
        aoi=aoi,
        adapter=InMemorySpatialAdapter(source),
        feature_id_field="NOT_REAL",
    )

    assert result.feature_count == 2
    ids = [feature.feature_id for feature in result.features]
    assert ids == ["303", "101"]  # inside, partial; these are not positions


@pytest.mark.parametrize(
    "null_id",
    [
        pytest.param(None, id="none"),
        pytest.param(float("nan"), id="nan"),
        pytest.param(pd.NA, id="pandas-na"),
    ],
)
def test_null_feature_id_falls_back_to_index_label(null_id):
    """An existing ID column with a null value uses the row's index label."""
    # Object dtype preserves each specific null representation for this test.
    row = pd.Series({"Id": null_id}, dtype=object)

    feature_id = _extract_feature_id(row, idx=73, feature_id_field="Id")

    assert feature_id == "73"


def test_zero_feature_id_is_preserved():
    """Zero is a valid ID and must not trigger the null-ID fallback."""
    row = pd.Series({"Id": 0}, dtype=object)

    feature_id = _extract_feature_id(row, idx=73, feature_id_field="Id")

    assert feature_id == "0"


@pytest.mark.parametrize(
    "make_keep_properties",
    [
        pytest.param(list, id="list"),
        pytest.param(iter, id="iterator"),
    ],
)
def test_keep_properties_accepts_reusable_and_one_shot_iterables(
    make_keep_properties,
):
    """Column selection must not consume the properties needed by results."""
    aoi = projected_operator_aoi()
    adapter = InMemorySpatialAdapter(_polygon_features(aoi))

    result = intersection(
        aoi=aoi,
        adapter=adapter,
        feature_id_field="Id",
        keep_properties=make_keep_properties(["Name"]),
    )

    assert adapter.last_options is not None
    assert set(adapter.last_options.keep_columns) == {"Id", "Name"}
    assert result.feature_count == 2
    assert [feature.properties for feature in result.features] == [
        {"Name": "inside"},
        {"Name": "partial"},
    ]


def test_default_read_options_overlay():
    options = _default_read_options(
        aoi=projected_operator_aoi(),
        feature_id_field="Id",
        keep_properties=["Type"],
    )

    assert options.spatial_filter is not None
    assert options.spatial_filter.predicate == "intersects"
    assert set(options.keep_columns) == {"Id", "Type"}


def test_build_results():
    """Point results preserve names and supply distinct fallback IDs."""
    aoi = projected_operator_aoi()
    source = _point_features(aoi).drop(columns=["Id"])

    result = intersection(
        aoi=aoi,
        adapter=InMemorySpatialAdapter(source),
        feature_id_field="FID",
        keep_properties=["Name"],
    )

    assert result.feature_count == 2
    assert len(result.features) == 2
    assert {feature.properties["Name"] for feature in result.features} == {
        "First",
        "Second",
    }
    ids = [feature.feature_id for feature in result.features]
    assert all(isinstance(value, str) and value for value in ids)
    assert len(set(ids)) == 2


def test_non_projected_aoi_rejected():
    adapter = InMemorySpatialAdapter()

    with pytest.raises(ValueError, match="projected CRS"):
        intersection(
            aoi=geographic_operator_aoi(),
            adapter=adapter,
            geom_type="polygon",
        )

    # The helper records a dictionary (even an empty one) whenever read runs.
    assert adapter.last_source_kwargs is None


def test_missing_aoi_crs_rejected_before_adapter_read():
    """An AOI with no CRS fails validation before requesting any data."""
    projected = projected_operator_aoi()
    aoi = AOIStub(
        gdf=aoi_gdf(list(projected.gdf.geometry), crs=None),
        aoi_id="missing_crs",
    )
    adapter = InMemorySpatialAdapter()

    with pytest.raises(ValueError, match="projected CRS"):
        intersection(aoi=aoi, adapter=adapter)

    assert adapter.last_source_kwargs is None


def test_operator_pushes_intersects():
    """The default request carries the AOI, columns, where clause and source."""
    aoi = projected_operator_aoi()
    adapter = InMemorySpatialAdapter()
    where = "STATUS = 'ACTIVE'"

    intersection(
        aoi=aoi,
        adapter=adapter,
        geom_type="polygon",
        feature_id_field="Id",
        keep_properties=["Name"],
        where=where,
        table="TEST_FEATURES",
    )

    options = adapter.last_options
    assert options is not None
    assert options.spatial_filter is not None
    assert options.spatial_filter.predicate == "intersects"
    assert options.spatial_filter.aoi.equals(aoi.gdf)
    assert options.spatial_filter.aoi.crs == aoi.gdf.crs
    assert options.where == where
    assert set(options.keep_columns) == {"Id", "Name"}
    assert adapter.last_target_crs == str(aoi.gdf.crs)
    assert adapter.last_source_kwargs == {"table": "TEST_FEATURES"}


def test_explicit_read_options_are_forwarded_unchanged():
    """Caller-supplied options take precedence over the default request."""
    aoi = projected_operator_aoi()
    adapter = InMemorySpatialAdapter()
    options = ReadOptions(
        spatial_filter=SpatialFilter(aoi=aoi.gdf, predicate="touches"),
        where="STATUS = 'CUSTOM'",
        keep_columns={"Name"},
    )

    intersection(
        aoi=aoi,
        adapter=adapter,
        read_options=options,
        feature_id_field="Id",
        keep_properties=["Name"],
        where="STATUS = 'DEFAULT'",
    )

    assert adapter.last_options is options
    assert options.spatial_filter is not None
    assert options.spatial_filter.predicate == "touches"
    assert options.where == "STATUS = 'CUSTOM'"
    assert set(options.keep_columns) == {"Name"}


@pytest.mark.parametrize(
    ("geom_type", "expected_type", "measure_attribute"),
    [
        pytest.param("polygon", PolyOverlayResult, "total_area", id="polygon"),
        pytest.param("line", LineOverlayResult, "total_length", id="line"),
        pytest.param("point", PointOverlayResult, "measure_value", id="point"),
    ],
)
def test_empty_dataset_returns_typed_zero_result(
    geom_type,
    expected_type,
    measure_attribute,
):
    """An empty adapter response honours the explicitly supplied dataset kind."""
    result = intersection(
        aoi=projected_operator_aoi(),
        adapter=InMemorySpatialAdapter(),
        geom_type=geom_type,
    )

    assert isinstance(result, expected_type)
    assert result.feature_count == 0
    assert result.measure_value == 0
    assert getattr(result, measure_attribute) == 0
    assert result.features == []


@pytest.mark.parametrize(
    ("make_features", "expected_type", "measure_attribute"),
    [
        pytest.param(
            _polygon_features, PolyOverlayResult, "total_area", id="polygon"
        ),
        pytest.param(
            _line_features, LineOverlayResult, "total_length", id="line"
        ),
        pytest.param(
            _point_features, PointOverlayResult, "measure_value", id="point"
        ),
    ],
)
def test_all_outside_features_return_typed_zero_result(
    make_features,
    expected_type,
    measure_attribute,
):
    """Nonempty input becomes an empty result after client-side filtering."""
    aoi = projected_operator_aoi()
    source = make_features(aoi)
    source = source.loc[source["Name"].str.lower() == "outside"].copy()
    assert len(source) == 1  # Keep this distinct from the empty-input case.

    # Infer the type from the geometry before the outside row is removed.
    result = intersection(aoi=aoi, adapter=InMemorySpatialAdapter(source))

    assert isinstance(result, expected_type)
    assert result.feature_count == 0
    assert result.measure_value == 0
    assert getattr(result, measure_attribute) == 0
    assert result.features == []


def test_polygon_sharing_only_aoi_edge_has_zero_overlap_area():
    """An edge intersection has length, but no polygon overlap area."""
    aoi = projected_operator_aoi()
    _, miny, maxx, _ = aoi.gdf.total_bounds
    source = aoi_gdf(
        [rect(maxx, miny + 100, maxx + 100, miny + 200)],
        crs=aoi.gdf.crs,
    )

    result = intersection(aoi=aoi, adapter=InMemorySpatialAdapter(source))

    assert isinstance(result, PolyOverlayResult)
    assert result.feature_count == 0
    assert result.total_area == 0.0
    assert result.features == []


def test_line_touching_aoi_at_endpoint_has_zero_overlap_length():
    """A point intersection does not contribute to a line's overlap length."""
    aoi = projected_operator_aoi()
    _, miny, maxx, _ = aoi.gdf.total_bounds
    source = aoi_gdf(
        [LineString([(maxx, miny + 100), (maxx + 100, miny + 100)])],
        crs=aoi.gdf.crs,
    )

    result = intersection(aoi=aoi, adapter=InMemorySpatialAdapter(source))

    assert isinstance(result, LineOverlayResult)
    assert result.feature_count == 0
    assert result.total_length == 0.0
    assert result.features == []


def test_line_along_aoi_boundary_contributes_its_overlap_length():
    """A 100 m line on the AOI edge still has 100 m of intersection."""
    aoi = projected_operator_aoi()
    _, miny, maxx, _ = aoi.gdf.total_bounds
    source = aoi_gdf(
        [LineString([(maxx, miny + 100), (maxx, miny + 200)])],
        crs=aoi.gdf.crs,
    )

    result = intersection(aoi=aoi, adapter=InMemorySpatialAdapter(source))

    assert result.feature_count == 1
    assert result.total_length == pytest.approx(100.0)
    assert [feature.measure for feature in result.features] == pytest.approx(
        [100.0]
    )


@pytest.mark.parametrize(
    ("make_features", "expected_type", "expected_measure"),
    [
        pytest.param(_point_features, PointOverlayResult, 2, id="point"),
        pytest.param(_line_features, LineOverlayResult, 300.0, id="line"),
    ],
)
def test_unknown_geom_type_falls_back_to_geometry_inference(
    make_features,
    expected_type,
    expected_measure,
):
    """The documented 'unknown' registry value uses the returned geometry."""
    aoi = projected_operator_aoi()

    result = intersection(
        aoi=aoi,
        adapter=InMemorySpatialAdapter(make_features(aoi)),
        geom_type="unknown",  # Deliberately exercise the documented fallback.
    )

    assert isinstance(result, expected_type)
    assert result.feature_count == 2
    assert result.measure_value == pytest.approx(expected_measure)


def test_overlay_includes_both_aoi_parts_but_excludes_the_gap():
    """A spanning feature overlaps two 100 x 100 m AOI parts: 20,000 m2."""
    x, y = 1_000_000, 1_000_000
    aoi = AOIStub(
        gdf=aoi_gdf(
            [
                rect(x, y, x + 100, y + 100),
                rect(x + 200, y, x + 300, y + 100),
            ]
        )
    )
    # This 30,000 m2 source feature covers both parts and the 10,000 m2 gap.
    source = aoi_gdf(
        [rect(x, y, x + 300, y + 100)],
        crs=aoi.gdf.crs,
        Name=["spanning"],
    )

    result = intersection(aoi=aoi, adapter=InMemorySpatialAdapter(source))

    assert result.feature_count == 1
    assert result.total_area == pytest.approx(20_000.0)
    assert [feature.measure for feature in result.features] == pytest.approx(
        [20_000.0]
    )


def test_pnt_geom_type():
    source = aoi_gdf([Point(0, 0)])
    assert _infer_geom_kind(source) == "point"


def test_line_geom_type():
    source = aoi_gdf([LineString([(0, 0), (100, 0)])])
    assert _infer_geom_kind(source) == "line"


def test_poly_geom_type():
    source = aoi_gdf([rect(0, 0, 100, 100)])
    assert _infer_geom_kind(source) == "polygon"


def test_empty_input():
    # Preserve the original expectation for an empty frame without geometry.
    assert _infer_geom_kind(gpd.GeoDataFrame()) == "polygon"


@pytest.mark.parametrize(
    (
        "make_features",
        "geom_type",
        "expected_type",
        "expected_count",
        "expected_measure",
    ),
    [
        pytest.param(
            _point_features,
            "polygon",
            PolyOverlayResult,
            0,
            0.0,
            id="points-as-polygon",
        ),
        pytest.param(
            _point_features,
            "line",
            LineOverlayResult,
            0,
            0.0,
            id="points-as-line",
        ),
        pytest.param(
            _polygon_features,
            "point",
            PointOverlayResult,
            2,
            2,
            id="polygons-as-point",
        ),
    ],
)
def test_geom_type_override_returns_correct_result_types(
    make_features,
    geom_type,
    expected_type,
    expected_count,
    expected_measure,
):
    """Explicit kinds control the result class and the way overlap is measured."""
    aoi = projected_operator_aoi()

    result = intersection(
        aoi=aoi,
        adapter=InMemorySpatialAdapter(make_features(aoi)),
        geom_type=geom_type,
    )

    assert isinstance(result, expected_type)
    assert result.feature_count == expected_count
    assert len(result.features) == expected_count
    assert result.measure_value == pytest.approx(expected_measure)
    if geom_type == "point":
        assert all(feature.measure is None for feature in result.features)
