from __future__ import annotations

from dataclasses import asdict

import geopandas as gpd
import pandas as pd
import pytest
from geopandas.testing import assert_geodataframe_equal
from pyproj import CRS
from shapely.geometry import (
    GeometryCollection,
    LineString,
    MultiLineString,
    MultiPoint,
    MultiPolygon,
    Point,
    Polygon,
)

from ast_engine.core.aoi.exceptions import (
    AOINormalizationError,
    DataCRSError,
    SpatialDataError,
    SpatialGeometryError,
    root_cause,
)
from ast_engine.core.aoi.models import AOINormalizationReport
from ast_engine.core.aoi.normalizer import AOINormalizer
from ast_engine.core.aoi.constants import DEFAULT_GEOM_FIELD
from ast_engine.tests.helpers.aoi_geometry import aoi_gdf, rect
from ast_engine.tests.helpers.aoi_requests import make_aoi_request


pytestmark = pytest.mark.unit


@pytest.fixture
def normalizer() -> AOINormalizer:
    return AOINormalizer()


def _overlapping_rectangles() -> list[Polygon]:
    """Two 10,000 m2 rectangles with a 5,000 m2 overlap; union = 15,000 m2."""
    return [rect(0, 0, 100, 100), rect(50, 0, 150, 100)]


def _extraction_counts(report: AOINormalizationReport) -> dict[str, int]:
    """Read the three extraction counters using shorter names in assertions."""
    return {
        "input": report.polygon_extract_input_feature_count,
        "retained": report.polygon_extract_output_feature_count,
        "dropped": report.polygon_extract_drop_count,
    }


# Geometry cleanup and extraction


def test_removes_null_and_empty_rows_without_losing_valid_polygon(normalizer):
    polygon = rect(0, 0, 100, 100)
    source = aoi_gdf(
        [None, polygon, Polygon(), GeometryCollection()],
        Id=[10, 20, 30, 40],
    )

    normalized = normalizer.normalize_aoi(
        gdf=source,
        request=make_aoi_request(dissolve_mode="preserve_features"),
    )

    assert normalized.gdf["Id"].tolist() == [20]
    assert normalized.gdf.geometry.iloc[0].equals(polygon)
    report = normalized.report
    assert report.input_feature_count == 4
    assert report.cleaned_feature_count == 1
    assert report.output_feature_count == 1
    assert report.null_or_empty_removed_count == 3
    assert report.repair_input_feature_count == 1
    assert report.repaired_feature_count == 0
    assert _extraction_counts(report) == {"input": 1, "retained": 1, "dropped": 0}


@pytest.mark.parametrize(
    ("nonpolygon", "component_count"),
    [
        pytest.param(Point(500, 500), 1, id="point"),
        pytest.param(LineString([(500, 0), (600, 0)]), 1, id="line"),
        pytest.param(MultiPoint([(500, 500), (600, 600)]), 2, id="multipoint"),
        pytest.param(
            MultiLineString([[(500, 0), (600, 0)], [(700, 0), (800, 0)]]),
            2,
            id="multiline",
        ),
    ],
)
def test_discards_nonpolygon_rows_and_counts_individual_components(
    normalizer, nonpolygon, component_count
):
    polygon = rect(0, 0, 100, 100)
    source = aoi_gdf([nonpolygon, polygon], Id=["discard", "keep"])

    normalized = normalizer.normalize_aoi(
        gdf=source,
        request=make_aoi_request(dissolve_mode="preserve_features"),
    )

    assert normalized.gdf["Id"].tolist() == ["keep"]
    assert normalized.gdf.geometry.iloc[0].equals(polygon)
    assert normalized.report.cleaned_feature_count == 1
    assert normalized.report.repaired_feature_count == 0
    assert _extraction_counts(normalized.report) == {
        "input": 1 + component_count,
        "retained": 1,
        "dropped": component_count,
    }


def test_secondary_geometry_columns_are_removed(normalizer):
    """Remove secondary geometries while preserving attributes and raw input."""
    expected = aoi_gdf(
        [
            rect(1_000_000, 1_000_000, 1_000_100, 1_000_100),
            rect(1_000_200, 1_000_000, 1_000_300, 1_000_100),
        ],
        Id=[10, 20],
        # Ordinary text despite the geometry-related column name.
        centroid=["first label", "second label"],
    )

    source = expected.copy()

    # Genuine secondary geometry columns: one point and one polygon.
    source["label_geometry"] = source.geometry.representative_point()
    source["buffer_geometry"] = source.geometry.buffer(10)

    original = source.copy()

    normalized = normalizer.normalize_aoi(
        gdf=source,
        request=make_aoi_request(dissolve_mode="preserve_features"),
    )

    assert "label_geometry" not in normalized.gdf.columns
    assert "buffer_geometry" not in normalized.gdf.columns

    # Expected fields, attribute values, polygons, and CRS survive.
    assert_geodataframe_equal(
        normalized.gdf,
        expected,
        check_like=True,
    )

    # The caller's input still includes its original secondary geometries.
    assert_geodataframe_equal(source, original)

    # Confirm removals were recorded without requiring exact note wording.
    notes = "\n".join(normalized.report.notes)
    assert "label_geometry" in notes
    assert "buffer_geometry" in notes


def test_repairs_bowtie_into_the_expected_two_triangles(normalizer):
    bowtie = Polygon([(0, 0), (100, 100), (0, 100), (100, 0), (0, 0)])
    expected = MultiPolygon(
        [
            Polygon([(0, 0), (100, 0), (50, 50)]),
            Polygon([(0, 100), (50, 50), (100, 100)]),
        ]
    )

    normalized = normalizer.normalize_aoi(
        gdf=aoi_gdf([bowtie]),
        request=make_aoi_request(dissolve_mode="preserve_features"),
    )

    geometry = normalized.gdf.geometry.iloc[0]
    assert geometry.is_valid
    assert geometry.equals(expected)
    assert geometry.area == pytest.approx(5_000.0)
    assert normalized.report.repair_input_feature_count == 1
    assert normalized.report.repaired_feature_count == 1
    assert _extraction_counts(normalized.report) == {"input": 2, "retained": 2, "dropped": 0}


def test_discards_feature_when_repair_leaves_only_linework(normalizer):
    collapsed = Polygon([(0, 0), (100, 0), (200, 0), (0, 0)])
    polygon = rect(300, 0, 400, 100)

    normalized = normalizer.normalize_aoi(
        gdf=aoi_gdf([collapsed, polygon], Id=["collapsed", "keep"]),
        request=make_aoi_request(dissolve_mode="preserve_features"),
    )

    assert normalized.gdf["Id"].tolist() == ["keep"]
    assert normalized.gdf.geometry.iloc[0].equals(polygon)
    assert normalized.report.repaired_feature_count == 1
    assert normalized.report.cleaned_feature_count == 1
    # The number of line pieces from repair need not be fixed across GEOS versions.
    assert normalized.report.polygon_extract_drop_count > 0


def test_mixed_collection_keeps_polygon_and_discards_external_line_and_point(normalizer):
    polygon = rect(0, 0, 100, 100)
    collection = GeometryCollection(
        [polygon, LineString([(500, 0), (600, 0)]), Point(700, 0)]
    )

    normalized = normalizer.normalize_aoi(
        gdf=aoi_gdf([collection]),
        request=make_aoi_request(),
    )

    assert normalized.gdf.geometry.iloc[0].equals(polygon)
    assert _extraction_counts(normalized.report) == {"input": 3, "retained": 1, "dropped": 2}


def test_nested_collections_retain_all_polygons_and_count_components(normalizer):
    first = rect(0, 0, 100, 100)
    second = rect(200, 0, 300, 100)
    third = rect(400, 0, 500, 100)
    collection = GeometryCollection(
        [
            first,
            GeometryCollection(
                [
                    MultiPolygon([second, third]),
                    GeometryCollection(
                        [LineString([(700, 0), (800, 0)]), Point(900, 0)]
                    ),
                ]
            ),
        ]
    )

    normalized = normalizer.normalize_aoi(
        gdf=aoi_gdf([collection]),
        request=make_aoi_request(),
    )

    assert normalized.gdf.geometry.iloc[0].equals(MultiPolygon([first, second, third]))
    assert normalized.gdf.geometry.iloc[0].area == pytest.approx(30_000.0)
    assert normalized.report.input_feature_count == 1
    assert normalized.report.output_feature_count == 1
    assert _extraction_counts(normalized.report) == {"input": 5, "retained": 3, "dropped": 2}


def test_collection_with_multipolygon_uses_consistent_component_counts(normalizer):
    polygons = MultiPolygon([rect(0, 0, 100, 100), rect(200, 0, 300, 100)])
    collection = GeometryCollection([polygons, LineString([(500, 0), (600, 0)])])

    normalized = normalizer.normalize_aoi(
        gdf=aoi_gdf([collection]),
        request=make_aoi_request(),
    )

    assert normalized.gdf.geometry.iloc[0].equals(polygons)
    assert _extraction_counts(normalized.report) == {"input": 3, "retained": 2, "dropped": 1}


def test_empty_members_of_a_collection_are_not_counted_as_components(normalizer):
    polygon = rect(0, 0, 100, 100)
    collection = GeometryCollection([polygon, Polygon(), Point(), GeometryCollection()])

    normalized = normalizer.normalize_aoi(
        gdf=aoi_gdf([collection]),
        request=make_aoi_request(),
    )

    assert normalized.gdf.geometry.iloc[0].equals(polygon)
    assert _extraction_counts(normalized.report) == {"input": 1, "retained": 1, "dropped": 0}


def test_extraction_counts_polygons_before_union_merges_them(normalizer):
    collection = GeometryCollection(_overlapping_rectangles())

    normalized = normalizer.normalize_aoi(
        gdf=aoi_gdf([collection]),
        request=make_aoi_request(),
    )

    geometry = normalized.gdf.geometry.iloc[0]
    assert isinstance(geometry, Polygon)
    assert geometry.equals(rect(0, 0, 150, 100))
    assert _extraction_counts(normalized.report) == {"input": 2, "retained": 2, "dropped": 0}


def test_preserves_polygon_hole_through_cleaning_and_union(normalizer):
    polygon = Polygon(
        [(0, 0), (100, 0), (100, 100), (0, 100)],
        holes=[[(25, 25), (75, 25), (75, 75), (25, 75)]],
    )

    normalized = normalizer.normalize_aoi(
        gdf=aoi_gdf([polygon]),
        request=make_aoi_request(dissolve_mode="full_union"),
    )

    geometry = normalized.gdf.geometry.iloc[0]
    assert geometry.equals(polygon)
    assert len(geometry.interiors) == 1
    assert geometry.area == pytest.approx(7_500.0)
    assert _extraction_counts(normalized.report) == {"input": 1, "retained": 1, "dropped": 0}


# CRS handling


def test_equivalent_crs_does_not_trigger_reprojection(normalizer):
    polygon = rect(1_000_000, 1_000_000, 1_000_100, 1_000_100)
    source = aoi_gdf([polygon], crs=CRS.from_epsg(3005).to_wkt())

    normalized = normalizer.normalize_aoi(
        gdf=source,
        request=make_aoi_request(target_crs="EPSG:3005"),
    )

    assert normalized.gdf.crs.to_epsg() == 3005
    assert normalized.gdf.geometry.iloc[0].equals(polygon)
    assert normalized.report.was_reprojected is False


@pytest.mark.parametrize(
    ("target_epsg", "expected"),
    [
        pytest.param(
            3005,
            rect(1_000_000, 1_000_000, 1_000_100, 1_000_100),
            id="bc-albers",
        ),
        pytest.param(
            26910,
            rect(500_000, 5_450_000, 500_100, 5_450_100),
            id="nad83-utm-10",
        ),
    ],
)
def test_reprojects_geographic_input_to_the_requested_crs(normalizer, target_epsg, expected):
    # Build geographic input from a known projected rectangle. Expected output is
    # that original rectangle, not another call to normalize_aoi or target to_crs.
    source = aoi_gdf([expected], crs=f"EPSG:{target_epsg}").to_crs(4326)

    normalized = normalizer.normalize_aoi(
        gdf=source,
        request=make_aoi_request(target_crs=f"EPSG:{target_epsg}"),
    )

    assert normalized.gdf.crs.to_epsg() == target_epsg
    actual = normalized.gdf.geometry.iloc[0]
    assert actual.hausdorff_distance(expected) < 0.00001
    assert actual.area == pytest.approx(10_000.0, abs=0.01)
    assert normalized.report.was_reprojected is True
    assert CRS.from_user_input(normalized.report.input_crs).to_epsg() == 4326
    assert CRS.from_user_input(normalized.report.output_crs).to_epsg() == target_epsg
    assert source.crs.to_epsg() == 4326


# Dissolve and overlap policies


def test_full_union_resolves_overlap_and_reports_policy_effects(normalizer):
    normalized = normalizer.normalize_aoi(
        gdf=aoi_gdf(_overlapping_rectangles()),
        request=make_aoi_request(dissolve_mode="full_union", allow_overlaps=False),
    )

    assert len(normalized.gdf) == 1
    assert normalized.gdf.geometry.iloc[0].equals(rect(0, 0, 150, 100))
    assert normalized.gdf.geometry.iloc[0].area == pytest.approx(15_000.0)
    report = normalized.report
    assert report.policy_name == "full_union"
    assert report.dissolve_fields_used == ()
    assert report.allow_overlaps is False
    assert report.policy_applied is True
    assert report.input_feature_count == 2
    assert report.cleaned_feature_count == 2
    assert report.policy_input_feature_count == 2
    assert report.policy_output_feature_count == 1
    assert report.output_feature_count == 1
    assert report.overlaps_detected_before_policy is True
    assert report.overlaps_present_after_policy is False
    assert report.overlaps_resolved_by_policy is True


def test_full_union_keeps_disconnected_polygons_in_one_multipolygon_row(normalizer):
    first = rect(0, 0, 100, 100)
    second = rect(200, 0, 300, 100)

    normalized = normalizer.normalize_aoi(
        gdf=aoi_gdf([first, second]),
        request=make_aoi_request(dissolve_mode="full_union"),
    )

    assert len(normalized.gdf) == 1
    assert normalized.gdf.geometry.iloc[0].equals(MultiPolygon([first, second]))
    assert normalized.report.overlaps_detected_before_policy is False
    assert normalized.report.overlaps_resolved_by_policy is False


def test_preserve_features_keeps_individual_geometry_attributes_and_row_order(normalizer):
    first = rect(0, 0, 100, 100)
    second = rect(200, 0, 300, 100)
    source = aoi_gdf([first, second], Id=["b", "a"], Name=["First", "Second"])
    source.index = pd.Index([90, 10], name="source_row")

    normalized = normalizer.normalize_aoi(
        gdf=source,
        request=make_aoi_request(dissolve_mode="preserve_features"),
    )

    assert normalized.gdf["Id"].tolist() == ["b", "a"]
    assert normalized.gdf["Name"].tolist() == ["First", "Second"]
    assert normalized.gdf.geometry.iloc[0].equals(first)
    assert normalized.gdf.geometry.iloc[1].equals(second)
    assert normalized.gdf.index.tolist() == [0, 1]
    assert normalized.report.policy_name == "preserve_features"
    assert normalized.report.policy_input_feature_count == 2
    assert normalized.report.policy_output_feature_count == 2


def test_preserve_features_leaves_multipolygon_as_one_feature(normalizer):
    geometry = MultiPolygon([rect(0, 0, 100, 100), rect(200, 0, 300, 100)])

    normalized = normalizer.normalize_aoi(
        gdf=aoi_gdf([geometry], Id=["multipart"]),
        request=make_aoi_request(dissolve_mode="preserve_features"),
    )

    assert len(normalized.gdf) == 1
    assert normalized.gdf.geometry.iloc[0].equals(geometry)
    assert normalized.gdf["Id"].tolist() == ["multipart"]
    assert normalized.report.output_feature_count == 1
    assert _extraction_counts(normalized.report) == {"input": 2, "retained": 2, "dropped": 0}


def test_preserve_features_retains_overlaps_when_allowed(normalizer):
    first, second = _overlapping_rectangles()

    normalized = normalizer.normalize_aoi(
        gdf=aoi_gdf([first, second], Id=["first", "second"]),
        request=make_aoi_request(dissolve_mode="preserve_features", allow_overlaps=True),
    )

    assert len(normalized.gdf) == 2
    assert normalized.gdf.geometry.iloc[0].equals(first)
    assert normalized.gdf.geometry.iloc[1].equals(second)
    assert normalized.gdf.geometry.area.sum() == pytest.approx(20_000.0)
    assert normalized.gdf.union_all().area == pytest.approx(15_000.0)
    assert normalized.report.allow_overlaps is True
    assert normalized.report.overlaps_detected_before_policy is True
    assert normalized.report.overlaps_present_after_policy is True
    assert normalized.report.overlaps_resolved_by_policy is False


@pytest.mark.parametrize(
    "second",
    [
        pytest.param(rect(50, 0, 150, 100), id="partial-overlap"),
        pytest.param(rect(25, 25, 75, 75), id="containment"),
        pytest.param(rect(0, 0, 100, 100), id="identical-polygon"),
    ],
)
def test_preserve_features_rejects_positive_area_overlap(normalizer, second):
    source = aoi_gdf([rect(0, 0, 100, 100), second])
    source.index = [101, 7]

    with pytest.raises(AOINormalizationError, match="allow_overlaps=False") as exc_info:
        normalizer.normalize_aoi(
            gdf=source,
            request=make_aoi_request(dissolve_mode="preserve_features", allow_overlaps=False),
        )

    assert isinstance(root_cause(exc_info.value), SpatialGeometryError)


@pytest.mark.parametrize(
    "second",
    [
        pytest.param(rect(100, 0, 200, 100), id="shared-edge"),
        pytest.param(rect(100, 100, 200, 200), id="shared-corner"),
    ],
)
def test_boundary_contact_is_allowed_when_area_overlaps_are_forbidden(normalizer, second):
    normalized = normalizer.normalize_aoi(
        gdf=aoi_gdf([rect(0, 0, 100, 100), second]),
        request=make_aoi_request(dissolve_mode="preserve_features", allow_overlaps=False),
    )

    assert len(normalized.gdf) == 2
    assert normalized.report.overlaps_detected_before_policy is False
    assert normalized.report.overlaps_present_after_policy is False


def test_by_fields_dissolves_matching_groups_and_preserves_other_groups(normalizer):
    source = aoi_gdf(
        [*_overlapping_rectangles(), rect(300, 0, 400, 100)],
        group_id=["A", "A", "B"],
    )
    source.index = [50, 20, 40]

    normalized = normalizer.normalize_aoi(
        gdf=source,
        request=make_aoi_request(
            dissolve_mode="by_fields",
            dissolve_fields=("group_id",),
            allow_overlaps=False,
        ),
    )

    # Key by group rather than depending on dissolve's sorting of group labels.
    geometries = normalized.gdf.set_index("group_id").geometry
    assert set(geometries.index) == {"A", "B"}
    assert geometries["A"].equals(rect(0, 0, 150, 100))
    assert geometries["B"].equals(rect(300, 0, 400, 100))
    report = normalized.report
    assert report.policy_name == "by_fields"
    assert report.dissolve_fields_used == ("group_id",)
    assert report.policy_input_feature_count == 3
    assert report.policy_output_feature_count == 2
    assert report.overlaps_detected_before_policy is True
    assert report.overlaps_present_after_policy is False
    assert report.overlaps_resolved_by_policy is True


def test_by_fields_uses_the_complete_grouping_key(normalizer):
    source = aoi_gdf(
        [
            rect(0, 0, 100, 100),
            rect(300, 0, 400, 100),
            rect(50, 0, 150, 100),
            rect(600, 0, 700, 100),
        ],
        group_id=["A", "A", "A", "B"],
        phase=["old", "new", "old", "old"],
    )

    normalized = normalizer.normalize_aoi(
        gdf=source,
        request=make_aoi_request(
            dissolve_mode="by_fields", dissolve_fields=("group_id", "phase")
        ),
    )

    geometries = normalized.gdf.set_index(["group_id", "phase"]).geometry
    assert set(geometries.index) == {("A", "old"), ("A", "new"), ("B", "old")}
    assert geometries.loc[("A", "old")].equals(rect(0, 0, 150, 100))
    assert geometries.loc[("A", "new")].equals(rect(300, 0, 400, 100))
    assert geometries.loc[("B", "old")].equals(rect(600, 0, 700, 100))
    assert normalized.report.dissolve_fields_used == ("group_id", "phase")


def test_by_fields_keeps_disconnected_members_of_one_group(normalizer):
    first = rect(0, 0, 100, 100)
    second = rect(200, 0, 300, 100)

    normalized = normalizer.normalize_aoi(
        gdf=aoi_gdf([first, second], group_id=["A", "A"]),
        request=make_aoi_request(dissolve_mode="by_fields", dissolve_fields=("group_id",)),
    )

    assert normalized.gdf["group_id"].tolist() == ["A"]
    assert normalized.gdf.geometry.iloc[0].equals(MultiPolygon([first, second]))
    assert normalized.report.output_feature_count == 1


def test_by_fields_rejects_remaining_overlap_between_different_groups(normalizer):
    with pytest.raises(AOINormalizationError, match="allow_overlaps=False") as exc_info:
        normalizer.normalize_aoi(
            gdf=aoi_gdf(_overlapping_rectangles(), group_id=["A", "B"]),
            request=make_aoi_request(
                dissolve_mode="by_fields", dissolve_fields=("group_id",), allow_overlaps=False
            ),
        )

    assert isinstance(root_cause(exc_info.value), SpatialGeometryError)


def test_by_fields_retains_overlap_between_groups_when_allowed(normalizer):
    first, second = _overlapping_rectangles()

    normalized = normalizer.normalize_aoi(
        gdf=aoi_gdf([first, second], group_id=["A", "B"]),
        request=make_aoi_request(
            dissolve_mode="by_fields", dissolve_fields=("group_id",), allow_overlaps=True
        ),
    )

    geometries = normalized.gdf.set_index("group_id").geometry
    assert set(geometries.index) == {"A", "B"}
    assert geometries["A"].equals(first)
    assert geometries["B"].equals(second)
    assert normalized.report.overlaps_detected_before_policy is True
    assert normalized.report.overlaps_present_after_policy is True
    assert normalized.report.overlaps_resolved_by_policy is False


def test_by_fields_rejects_a_missing_grouping_column(normalizer):
    with pytest.raises(AOINormalizationError, match="missing_field") as exc_info:
        normalizer.normalize_aoi(
            gdf=aoi_gdf([rect(0, 0, 100, 100)], group_id=["A"]),
            request=make_aoi_request(
                dissolve_mode="by_fields", dissolve_fields=("missing_field",)
            ),
        )

    assert isinstance(root_cause(exc_info.value), SpatialDataError)


@pytest.mark.parametrize(
    "missing",
    [
        pytest.param(None, id="none"),
        pytest.param(float("nan"), id="nan"),
        pytest.param(pd.NA, id="pd-NA"),
    ],
)
def test_by_fields_combines_polygons_with_missing_grouping_values(
    normalizer,
    missing,
):
    """Polygons with the same region and missing group_id dissolve together."""
    named_polygon = rect(0, 0, 100, 100)
    missing_first = rect(200, 0, 300, 100)
    missing_second = rect(400, 0, 500, 100)

    source = aoi_gdf(
        [named_polygon, missing_first, missing_second],
        region=["North", "North", "North"],
        group_id=["A", missing, missing],
    )

    normalized = normalizer.normalize_aoi(
        gdf=source,
        request=make_aoi_request(
            dissolve_mode="by_fields",
            dissolve_fields=("region", "group_id"),
        ),
    )

    result = normalized.gdf

    # Three input features become two groups.
    assert len(result) == 2
    assert result["region"].tolist() == ["North", "North"]

    named_group = result.loc[result["group_id"].eq("A")]
    missing_group = result.loc[result["group_id"].isna()]

    assert len(named_group) == 1
    assert len(missing_group) == 1

    assert named_group.geometry.iloc[0].equals(named_polygon)

    # Both disconnected polygons must survive within the missing-key group.
    expected_missing = MultiPolygon([missing_first, missing_second])
    actual_missing = missing_group.geometry.iloc[0]

    assert actual_missing.equals(expected_missing)
    assert actual_missing.area == pytest.approx(20_000.0)
    assert result.geometry.area.sum() == pytest.approx(30_000.0)

    assert normalized.report.policy_applied is True
    assert normalized.report.policy_input_feature_count == 3
    assert normalized.report.policy_output_feature_count == 2


# Invalid source data and exception contract


@pytest.mark.parametrize(
    "make_input",
    [
        pytest.param(lambda: None, id="none"),
        pytest.param(lambda: pd.DataFrame({"Id": [1]}), id="ordinary-dataframe"),
        pytest.param(lambda: aoi_gdf([]), id="empty-geodataframe"),
    ],
)
def test_rejects_missing_wrong_type_or_empty_input(normalizer, make_input):
    # Factories avoid sharing mutable frames between parameterized test cases.
    with pytest.raises(AOINormalizationError) as exc_info:
        normalizer.normalize_aoi(gdf=make_input(), request=make_aoi_request())

    assert isinstance(root_cause(exc_info.value), SpatialDataError)


def test_rejects_missing_source_crs_with_crs_cause(normalizer):
    with pytest.raises(AOINormalizationError) as exc_info:
        normalizer.normalize_aoi(
            gdf=aoi_gdf([rect(0, 0, 100, 100)], crs=None),
            request=make_aoi_request(),
        )

    assert isinstance(root_cause(exc_info.value), DataCRSError)


def test_rejects_missing_active_geometry_with_geometry_cause(normalizer):
    """Regression: check_gdf must check geometry before accessing gdf.crs."""
    source = gpd.GeoDataFrame({"Id": [1]})

    with pytest.raises(AOINormalizationError) as exc_info:
        normalizer.normalize_aoi(gdf=source, request=make_aoi_request())

    # The SpatialGeometryError may itself chain GeoPandas' AttributeError;
    # check the normalizer's immediate cause, not the deepest exception.
    assert isinstance(exc_info.value.__cause__, SpatialGeometryError)


@pytest.mark.parametrize(
    "make_geometries",
    [
        pytest.param(lambda: [None, None], id="all-null"),
        pytest.param(lambda: [Polygon(), GeometryCollection()], id="all-empty"),
        pytest.param(
            lambda: [Point(0, 0), LineString([(0, 0), (100, 100)])],
            id="points-and-lines",
        ),
        pytest.param(
            lambda: [Polygon([(0, 0), (100, 0), (200, 0), (0, 0)])],
            id="repair-leaves-no-polygon",
        ),
    ],
)
def test_rejects_input_when_cleanup_leaves_no_polygon(normalizer, make_geometries):
    with pytest.raises(AOINormalizationError) as exc_info:
        normalizer.normalize_aoi(
            gdf=aoi_gdf(make_geometries()), request=make_aoi_request()
        )

    assert isinstance(root_cause(exc_info.value), SpatialGeometryError)


# Column names, input ownership, and per-call report state


@pytest.mark.parametrize(
    ("mode", "fields"),
    [
        pytest.param("preserve_features", (), id="preserve-features"),
        pytest.param("by_fields", ("group_id",), id="by-fields"),
    ],
)
def test_normalization_preserves_custom_active_geometry_column(normalizer, mode, fields):
    polygon = rect(0, 0, 100, 100)
    source = aoi_gdf([polygon], group_id=["A"]).rename_geometry("shape")

    normalized = normalizer.normalize_aoi(
        gdf=source,
        request=make_aoi_request(dissolve_mode=mode, dissolve_fields=fields),
    )

    assert normalized.gdf.geometry.name == DEFAULT_GEOM_FIELD
    assert normalized.gdf.geometry.iloc[0].equals(polygon)
    assert normalized.gdf["group_id"].tolist() == ["A"]


@pytest.mark.parametrize(
    ("mode", "fields"),
    [
        pytest.param("full_union", (), id="full-union"),
        pytest.param("preserve_features", (), id="preserve-features"),
        pytest.param("by_fields", ("group_id",), id="by-fields"),
    ],
)
def test_normalization_and_editing_output_do_not_mutate_source(normalizer, mode, fields):
    bowtie = Polygon([(300, 0), (400, 100), (300, 100), (400, 0), (300, 0)])
    source = aoi_gdf(
        [rect(0, 0, 100, 100), bowtie, None],
        group_id=["A", "A", "unused"],
        Name=["Valid", "Invalid", "Null"],
    ).rename_geometry("shape")
    source.index = pd.Index([40, 50, 60], name="source_row")
    before = source.copy(deep=True)

    normalized = normalizer.normalize_aoi(
        gdf=source,
        request=make_aoi_request(dissolve_mode=mode, dissolve_fields=fields),
    )

    assert_geodataframe_equal(source, before)
    normalized.gdf.loc[0, normalized.gdf.geometry.name] = rect(1_000, 0, 1_100, 100)
    normalized.gdf["output_only"] = "changed"
    assert_geodataframe_equal(source, before)


def test_reusing_normalizer_does_not_leak_report_state_between_calls(normalizer):
    bowtie = Polygon([(0, 0), (100, 100), (0, 100), (100, 0), (0, 0)])
    first = normalizer.normalize_aoi(
        gdf=aoi_gdf([None, bowtie]),
        request=make_aoi_request(),
    )
    first_report_before = asdict(first.report)

    second = normalizer.normalize_aoi(
        gdf=aoi_gdf([rect(300, 0, 400, 100)]),
        request=make_aoi_request(),
    )

    assert first.report.repaired_feature_count == 1
    assert first.report.null_or_empty_removed_count == 1
    assert second.report.input_feature_count == 1
    assert second.report.cleaned_feature_count == 1
    assert second.report.repaired_feature_count == 0
    assert second.report.null_or_empty_removed_count == 0
    assert _extraction_counts(second.report) == {"input": 1, "retained": 1, "dropped": 0}
    assert first.report is not second.report
    assert asdict(first.report) == first_report_before
