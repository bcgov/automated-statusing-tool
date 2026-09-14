from __future__ import annotations

from dataclasses import replace

import geopandas as gpd
import pandas as pd
import pytest
from geopandas.testing import assert_geodataframe_equal
from pyproj import CRS
from shapely.geometry import GeometryCollection, LineString, MultiPolygon, Point, Polygon

from ast_engine.core.aoi.exceptions import (
    AOIInspectionError,
    DataCRSError,
    SpatialDataError,
    SpatialGeometryError,
)
from ast_engine.core.aoi.inspector import AOIInspector
from ast_engine.core.aoi.models import AOIPart, AOIProperties
from ast_engine.tests.helpers.aoi_geometry import aoi_gdf, rect


pytestmark = pytest.mark.unit


@pytest.fixture
def inspector() -> AOIInspector:
    return AOIInspector()


def _part(
    polygon: Polygon,
    *,
    area_ha: float,
    vertex_count: int,
    index: int = 1,
    crs="EPSG:3005",
) -> AOIPart:
    """Build one input record without invoking any processing-stage factory.

    Area and vertex values are deliberately required: tests state the expected
    metadata instead of obtaining their answers from production calculators.
    The GDF and bounds complete the model; inspect() aggregates its cached fields.
    """
    return AOIPart(
        part_id=f"test_aoi_part_{index:04d}",
        parent_aoi_id="test_aoi",
        geom_type="Polygon",
        part_index=index,
        gdf=aoi_gdf([polygon], crs=crs),
        bounds=tuple(float(value) for value in polygon.bounds),
        area_ha=area_ha,
        vertex_count=vertex_count,
        has_z=False,
        has_m=False,
    )


# Footprint measurements and aggregation


def test_single_polygon_has_expected_properties(inspector):
    polygon = rect(100, 200, 300, 350)  # 200 m x 150 m = 3 ha.
    source = aoi_gdf([polygon])
    parts = (_part(polygon, area_ha=3.0, vertex_count=5),)

    props = inspector.inspect(source, parts)

    assert isinstance(props, AOIProperties)
    assert props.crs_epsg == 3005
    assert props.crs_string == "EPSG:3005"
    assert props.footprint_area_ha == pytest.approx(3.0)
    assert props.parts_area_ha == pytest.approx(3.0)
    assert props.parts_to_footprint_ratio == pytest.approx(1.0)
    assert props.bounds == pytest.approx((100.0, 200.0, 300.0, 350.0))
    assert props.feature_count == 1
    assert props.part_count == 1
    assert props.geometry_type == "Polygon"
    assert props.vertex_count == 5
    assert props.max_vertices_per_part == 5
    assert props.has_z is False
    assert props.has_m is False


@pytest.mark.parametrize(
    ("second_bounds", "second_area_ha", "expected_footprint_ha", "expected_bounds"),
    [
        pytest.param(
            (200, 0, 300, 100), 1.0, 2.0, (0, 0, 300, 100), id="disjoint"
        ),
        pytest.param(
            (100, 0, 200, 100), 1.0, 2.0, (0, 0, 200, 100), id="shared-edge"
        ),
        pytest.param(
            (50, 0, 150, 100), 1.0, 1.5, (0, 0, 150, 100), id="overlap"
        ),
        pytest.param(
            (25, 25, 75, 75), 0.25, 1.0, (0, 0, 100, 100), id="contained"
        ),
        pytest.param(
            (0, 0, 100, 100), 1.0, 1.0, (0, 0, 100, 100), id="duplicate"
        ),
    ],
)
def test_footprint_uses_union_while_part_area_keeps_every_part(
    inspector, second_bounds, second_area_ha, expected_footprint_ha, expected_bounds
):
    """Union removes double counting; part totals retain the supplied parts.

    Overlap can remain when the upstream normalization policy preserves it.
    In the disjoint case, the gap in the overall bounds contributes no area.
    """
    first = rect(0, 0, 100, 100)
    second = rect(*second_bounds)
    source = aoi_gdf([first, second])
    parts = (
        _part(first, area_ha=1.0, vertex_count=5),
        _part(second, area_ha=second_area_ha, vertex_count=5, index=2),
    )

    props = inspector.inspect(source, parts)

    expected_parts_ha = 1.0 + second_area_ha
    assert props.footprint_area_ha == pytest.approx(expected_footprint_ha)
    assert props.parts_area_ha == pytest.approx(expected_parts_ha)
    assert props.parts_to_footprint_ratio == pytest.approx(
        expected_parts_ha / expected_footprint_ha
    )
    assert props.bounds == pytest.approx(expected_bounds)
    assert props.feature_count == 2
    assert props.part_count == 2
    # These describe the input rows and part metadata, even after union.
    assert props.geometry_type == "Polygon"
    assert props.vertex_count == 10
    assert props.max_vertices_per_part == 5


def test_multipolygon_has_one_feature_and_two_parts(inspector):
    first = rect(0, 0, 100, 100)  # 1 ha.
    second = rect(200, 0, 400, 100)  # 2 ha.
    source = aoi_gdf([MultiPolygon([first, second])])
    parts = (
        _part(first, area_ha=1.0, vertex_count=5),
        _part(second, area_ha=2.0, vertex_count=5, index=2),
    )

    props = inspector.inspect(source, parts)

    assert props.feature_count == 1
    assert props.part_count == 2
    assert props.geometry_type == "MultiPolygon"
    assert props.footprint_area_ha == pytest.approx(3.0)
    assert props.parts_area_ha == pytest.approx(3.0)
    assert props.parts_to_footprint_ratio == pytest.approx(1.0)
    assert props.bounds == pytest.approx((0, 0, 400, 100))
    assert props.vertex_count == 10
    assert props.max_vertices_per_part == 5


@pytest.mark.parametrize("reverse_rows", [False, True], ids=["single-first", "multi-first"])
def test_mixed_geometry_type_is_sorted_and_independent_of_row_order(inspector, reverse_rows):
    first = rect(0, 0, 100, 100)
    second = rect(200, 0, 400, 100)
    third = rect(500, 0, 800, 100)
    rows = [first, MultiPolygon([second, third])]
    if reverse_rows:
        rows.reverse()
    source = aoi_gdf(rows)
    parts = (
        _part(first, area_ha=1.0, vertex_count=5),
        _part(second, area_ha=2.0, vertex_count=5, index=2),
        _part(third, area_ha=3.0, vertex_count=5, index=3),
    )

    props = inspector.inspect(source, parts)

    assert props.geometry_type == "Mixed[MultiPolygon, Polygon]"
    assert props.feature_count == 2
    assert props.part_count == 3
    assert props.footprint_area_ha == pytest.approx(6.0)
    assert props.parts_area_ha == pytest.approx(6.0)
    assert props.parts_to_footprint_ratio == pytest.approx(1.0)
    assert props.vertex_count == 15


def test_hole_area_is_excluded_and_vertex_total_differs_from_maximum(inspector):
    holed = Polygon(
        [(0, 0), (200, 0), (200, 200), (0, 200)],
        holes=[[(50, 50), (150, 50), (150, 150), (50, 150)]],
    )  # 4 ha outer square minus 1 ha hole = 3 ha; two closed rings = 10 vertices.
    triangle = Polygon([(300, 0), (400, 0), (300, 100)])  # 0.5 ha, 4 vertices.
    source = aoi_gdf([holed, triangle])
    parts = (
        _part(holed, area_ha=3.0, vertex_count=10),
        _part(triangle, area_ha=0.5, vertex_count=4, index=2),
    )

    props = inspector.inspect(source, parts)

    assert props.footprint_area_ha == pytest.approx(3.5)
    assert props.parts_area_ha == pytest.approx(3.5)
    assert props.parts_to_footprint_ratio == pytest.approx(1.0)
    assert props.bounds == pytest.approx((0, 0, 400, 200))
    assert props.vertex_count == 14
    assert props.max_vertices_per_part == 10


@pytest.mark.parametrize(
    ("flags", "expected_z", "expected_m"),
    [
        pytest.param(
            ((False, False), (False, False), (False, False)), False, False, id="neither"
        ),
        pytest.param(
            ((False, False), (True, False), (False, False)), True, False, id="z-in-middle"
        ),
        pytest.param(
            ((False, False), (False, True), (False, False)), False, True, id="m-in-middle"
        ),
        pytest.param(
            ((True, False), (False, False), (False, True)), True, True, id="separate-z-and-m"
        ),
        pytest.param(
            ((True, True), (False, False), (False, False)), True, True, id="both-in-first"
        ),
    ],
)
def test_dimension_flags_aggregate_supplied_part_metadata(inspector, flags, expected_z, expected_m):
    """Test any-part aggregation; coordinate detection belongs to the part builder.

    Controlled flags are supplied independently of the simple 2D AOI geometry,
    so this test cannot pass by scanning the AOI instead of reading part metadata.
    """
    polygons = [rect(x, 0, x + 100, 100) for x in (0, 200, 400)]
    parts = tuple(
        replace(
            _part(polygon, area_ha=1.0, vertex_count=5, index=index),
            has_z=has_z,
            has_m=has_m,
        )
        for index, (polygon, (has_z, has_m)) in enumerate(zip(polygons, flags), start=1)
    )

    props = inspector.inspect(aoi_gdf(polygons), parts)

    assert props.has_z is expected_z
    assert props.has_m is expected_m


# CRS, active geometry, and independence of input/output objects


@pytest.mark.parametrize(
    ("crs_value", "expected_epsg"),
    [
        pytest.param("EPSG:26910", 26910, id="another-projected-metre-crs"),
        pytest.param(
            "+proj=aeqd +lat_0=53.123456 +lon_0=-123.654321 "
            "+datum=WGS84 +units=m +type=crs",
            None,
            id="projected-crs-without-epsg",
        ),
    ],
)
def test_crs_metadata_preserves_the_input_projected_crs(inspector, crs_value, expected_epsg):
    """The inspector reports the supplied CRS; reprojection belongs upstream."""
    polygon = rect(500_000, 6_000_000, 500_100, 6_000_100)
    source = aoi_gdf([polygon], crs=crs_value)
    parts = (_part(polygon, area_ha=1.0, vertex_count=5, crs=crs_value),)

    props = inspector.inspect(source, parts)

    assert props.crs_epsg == expected_epsg
    assert CRS.from_user_input(props.crs_string) == source.crs
    assert props.footprint_area_ha == pytest.approx(1.0)
    assert props.bounds == pytest.approx((500_000, 6_000_000, 500_100, 6_000_100))


def test_custom_active_geometry_column_is_used(inspector):
    polygon = rect(10, 20, 110, 220)  # 2 ha.
    source = aoi_gdf([polygon]).rename_geometry("shape")
    # An ordinary attribute with this name must not replace the active geometry.
    source["geometry"] = ["descriptive attribute"]
    parts = (_part(polygon, area_ha=2.0, vertex_count=5),)

    props = inspector.inspect(source, parts)

    assert props.footprint_area_ha == pytest.approx(2.0)
    assert props.bounds == pytest.approx((10, 20, 110, 220))
    assert props.geometry_type == "Polygon"
    assert source.geometry.name == "shape"
    assert source["geometry"].tolist() == ["descriptive attribute"]


def test_inspection_preserves_source_and_part_frames_with_duplicate_row_labels(inspector):
    first = rect(0, 0, 100, 100)
    second = rect(200, 0, 300, 100)
    source = aoi_gdf([first, second], Name=["first", "second"], group_id=[None, "A"])
    source.index = pd.Index([42, 42], name="source_row")
    parts = (
        _part(first, area_ha=1.0, vertex_count=5),
        _part(second, area_ha=1.0, vertex_count=5, index=2),
    )
    for part in parts:
        part.gdf["note"] = ["keep this"]
    source_before = source.copy(deep=True)
    part_frames_before = [part.gdf.copy(deep=True) for part in parts]

    props = inspector.inspect(source, parts)

    assert props.feature_count == 2
    assert props.part_count == 2
    assert props.footprint_area_ha == pytest.approx(2.0)
    assert_geodataframe_equal(source, source_before)
    for part, before in zip(parts, part_frames_before):
        assert_geodataframe_equal(part.gdf, before)


def test_reusing_inspector_returns_independent_snapshots(inspector):
    large = rect(0, 0, 300, 100)
    source = aoi_gdf([large])
    parts = (_part(large, area_ha=3.0, vertex_count=5),)

    first = inspector.inspect(source, parts)
    repeated = inspector.inspect(source, parts)
    assert repeated == first

    small = rect(400, 0, 500, 100)
    later = inspector.inspect(
        aoi_gdf([small]), (_part(small, area_ha=1.0, vertex_count=5),)
    )

    assert later.footprint_area_ha == pytest.approx(1.0)
    assert later.parts_area_ha == pytest.approx(1.0)
    assert later.bounds == pytest.approx((400, 0, 500, 100))
    assert first.footprint_area_ha == pytest.approx(3.0)
    assert first.parts_area_ha == pytest.approx(3.0)
    assert first.bounds == pytest.approx((0, 0, 300, 100))


# Invalid input and the inspection-stage exception contract


def test_empty_parts_are_rejected_as_an_inspection_error(inspector):
    source = aoi_gdf([rect(0, 0, 100, 100)])

    with pytest.raises(AOIInspectionError) as exc_info:
        inspector.inspect(source, ())

    assert isinstance(exc_info.value.__cause__, SpatialGeometryError)
    assert "no AOI parts" in str(exc_info.value.__cause__)


@pytest.mark.parametrize(
    ("make_source", "expected_cause"),
    [
        pytest.param(lambda: None, SpatialDataError, id="none"),
        pytest.param(
            lambda: pd.DataFrame({"Name": ["not a GeoDataFrame"]}),
            SpatialDataError,
            id="ordinary-dataframe",
        ),
        pytest.param(lambda: aoi_gdf([]), SpatialDataError, id="empty-geodataframe"),
        pytest.param(
            lambda: aoi_gdf([rect(0, 0, 100, 100)], crs=None),
            DataCRSError,
            id="missing-crs",
        ),
        pytest.param(
            lambda: aoi_gdf([rect(-124, 49, -123, 50)], crs="EPSG:4326"),
            DataCRSError,
            id="geographic-crs",
        ),
        pytest.param(
            lambda: gpd.GeoDataFrame({"Name": ["no active geometry"]}),
            SpatialGeometryError,
            id="missing-active-geometry",
        ),
    ],
)
def test_bad_data_and_crs_errors_are_wrapped_for_the_inspection_stage(
    inspector, make_source, expected_cause
):
    """Active regressions for the proposed consistent expected-error contract.

    Using an actual bad input keeps the real check_gdf() boundary under test.
    Inspect the immediate cause: a lower-level pyproj/GeoPandas exception may
    exist further down the chain and is not the domain exception wrapped here.
    """
    polygon = rect(0, 0, 100, 100)
    parts = (_part(polygon, area_ha=1.0, vertex_count=5),)

    with pytest.raises(AOIInspectionError) as exc_info:
        inspector.inspect(make_source(), parts)

    assert isinstance(exc_info.value.__cause__, expected_cause)


@pytest.mark.parametrize(
    "make_bad_geometry",
    [
        pytest.param(lambda: None, id="null"),
        pytest.param(Polygon, id="empty-polygon"),
        pytest.param(lambda: Point(200, 0), id="point"),
        pytest.param(lambda: LineString([(200, 0), (300, 100)]), id="line"),
        pytest.param(
            lambda: GeometryCollection([rect(200, 0, 300, 100), Point(400, 0)]),
            id="collection-needing-normalization",
        ),
        pytest.param(
            lambda: Polygon([(200, 0), (300, 100), (200, 100), (300, 0)]),
            id="self-intersecting-polygon",
        ),
        pytest.param(
            lambda: MultiPolygon([rect(200, 0, 300, 100), rect(250, 0, 350, 100)]),
            id="invalid-overlapping-multipolygon",
        ),
    ],
)
def test_unnormalized_geometry_is_rejected_even_alongside_a_valid_row(
    inspector, make_bad_geometry
):
    """The inspector must reject unusable rows instead of silently cleaning them."""
    good = rect(0, 0, 100, 100)
    source = aoi_gdf([good, make_bad_geometry()])
    parts = (_part(good, area_ha=1.0, vertex_count=5),)

    with pytest.raises(AOIInspectionError) as exc_info:
        inspector.inspect(source, parts)

    assert isinstance(exc_info.value.__cause__, SpatialGeometryError)


@pytest.mark.parametrize(
    "failure_type",
    [
        pytest.param(AOIInspectionError, id="existing-inspection-error"),
        pytest.param(RuntimeError, id="unexpected-error"),
    ],
)
def test_existing_stage_errors_and_unexpected_errors_propagate_unchanged(
    inspector, monkeypatch, failure_type
):
    """Preserve exception identity rather than hiding it in another wrapper."""
    polygon = rect(0, 0, 100, 100)
    source = aoi_gdf([polygon])
    parts = (_part(polygon, area_ha=1.0, vertex_count=5),)
    failure = failure_type("injected union failure")

    def fail_union(*args, **kwargs):
        raise failure

    # Patch only this frame's geometry operation; all earlier validation is real.
    monkeypatch.setattr(source, "union_all", fail_union)

    with pytest.raises(failure_type) as exc_info:
        inspector.inspect(source, parts)

    assert exc_info.value is failure
