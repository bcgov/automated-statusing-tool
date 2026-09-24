from __future__ import annotations

import pytest

from ast_engine.tests.helpers.aoi_requests import (
    build_aoi_request,
    full_union_request,
    preserve_features_request,
)

from ast_engine.tests.helpers.aoi_assertions import (
    assert_successful_aoi_build,
    assert_validation_issue_codes,
)
from ast_engine.tests.helpers.aoi_geometry import (
    overlapping_polygons_gdf,
    multipolygon_gdf,
    missing_crs_gdf,
    squares_gdf,
)

from ast_engine.core.aoi.exceptions import (
    AOIBuildError,
    DataCRSError,
    SpatialGeometryError,
    root_cause
)

pytestmark = pytest.mark.unit


def test_builder_handles_overlapping_polygons_with_full_union(
    aoi_builder,
):
    """Test that the AOIBuilder can handle overlapping polygons when using the "full_union" dissolve mode."""

    request = build_aoi_request(
        spec=full_union_request(),
        raw_gdf=overlapping_polygons_gdf(),
    )

    result = aoi_builder.build_from_request(request)

    assert_successful_aoi_build(result)

    assert result.aoi.part_count == 1
    assert result.aoi.footprint_area_ha == pytest.approx(1.96)
    assert result.aoi.parts_area_ha == pytest.approx(1.96)
    assert result.aoi.footprint_area_ha == result.aoi.parts_area_ha
    assert result.normalization_report.policy_name == "full_union"
    assert not result.normalization_report.overlaps_present_after_policy


def test_builder_splits_multipolygon_into_parts(aoi_builder):
    """Test that the AOIBuilder can handle a multipolygon by splitting it into separate parts."""
    request = build_aoi_request(
        spec=full_union_request(),
        raw_gdf=multipolygon_gdf(),
    )

    result = aoi_builder.build_from_request(request)

    assert_successful_aoi_build(result)
    assert result.aoi.part_count == 2
    assert len(result.aoi.parts) == 2


def test_builder_returns_invalid_result_when_validation_reports_errors(
    aoi_builder,
):
    """Test that the AOIBuilder can handle a request that fails validation due to large parts."""

    request = build_aoi_request(
        spec=preserve_features_request(),
        raw_gdf=squares_gdf(
            count=5,
            size=10000,
            overlap=True,
            group_id=['A', 'B', 'C', 'D', 'E'],
        )
    )

    result = aoi_builder.build_from_request(request)

    assert_validation_issue_codes(
        result,
        expected_codes=[
            "LARGE_PART",
        ],
    )

    assert result.validation.is_valid is False
    assert result.aoi.part_count == 5
    assert len(result.aoi.parts) == 5

    large_part_errors = [
        issue
        for issue in result.validation.errors
        if issue.code == "LARGE_PART"
    ]

    assert len(large_part_errors) == 5


def test_builder_rejects_missing_crs(
    aoi_builder,
):
    """Test that the AOIBuilder rejects a request with a GeoDataFrame that has no CRS defined."""
    request = build_aoi_request(
        spec=full_union_request(),
        raw_gdf=missing_crs_gdf(),
    )

    with pytest.raises(AOIBuildError) as exc_info:
        aoi_builder.build_from_request(request)

    assert isinstance(root_cause(exc_info.value), DataCRSError)

    error = exc_info.value
    assert error.stage == "normalization"
    assert error.aoi_id == request.spec.aoi_id


def test_builder_rejects_overlaps_when_not_allowed(
    aoi_builder,
):
    """Test that the AOIBuilder rejects a request with overlapping polygons when overlaps are not allowed."""

    request = build_aoi_request(
        spec=preserve_features_request(allow_overlaps=False),
        raw_gdf=overlapping_polygons_gdf(),
    )

    with pytest.raises(AOIBuildError) as exc_info:
        aoi_builder.build_from_request(request)

    assert isinstance(root_cause(exc_info.value), SpatialGeometryError)

    error = exc_info.value
    assert error.stage == "normalization"
    assert error.aoi_id == request.spec.aoi_id