# tests/unit/aoi/test_aoi_builder.py

from __future__ import annotations

import pytest

from ast_engine.core.aoi.exceptions import (
    AOIBuildError,
    DataCRSError,
    SpatialGeometryError,
    root_cause
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
from ast_engine.tests.helpers.aoi_requests import full_union_request, preserve_features_request

pytestmark = pytest.mark.unit

### Tests for successful AOI builds #####
def test_builder_handles_overlapping_polygons_with_full_union(
    aoi_builder,
    make_aoi_build_request,
):
    build_request = make_aoi_build_request(
        spec=full_union_request(),
        raw_gdf=overlapping_polygons_gdf(),
    )

    result = aoi_builder.build_from_request(build_request)

    assert_successful_aoi_build(result)

    assert result.aoi.part_count >= 1
    assert result.normalization_report.policy_name == "full_union"
    assert not result.normalization_report.overlaps_present_after_policy



def test_builder_splits_multipolygon_into_parts(
    aoi_builder,
    make_aoi_build_request,
):
    build_request = make_aoi_build_request(
        spec=full_union_request(),
        raw_gdf=multipolygon_gdf(),
    )

    result = aoi_builder.build_from_request(build_request)

    assert_successful_aoi_build(result)

    assert result.aoi.part_count == 2
    assert len(result.aoi.parts) == 2


### Tests for unsuccessful validation from AOI builds #####
def test_builder_fail_validation(
    aoi_builder,
    make_aoi_build_request,
):
    build_request = make_aoi_build_request(
        spec=preserve_features_request(),
        raw_gdf=squares_gdf(
            count=5,
            size=10000,
            overlap=True,
            group_id=['A', 'B', 'C', 'D', 'E'],
        )
    )

    result = aoi_builder.build_from_request(build_request)

    assert_validation_issue_codes(
        result,
        expected_codes=[
            "LARGE_PART",
        ],
    )

    assert result.aoi.part_count == 5
    assert len(result.aoi.parts) == 5


### Tests for failures to build AOI due to invalid input data. Should raise AOIBuildError #####
def test_builder_rejects_missing_crs(
    aoi_builder,
    make_aoi_build_request,
):
    build_request = make_aoi_build_request(
        spec=full_union_request(),
        raw_gdf=missing_crs_gdf(),
    )

    with pytest.raises(AOIBuildError) as exc_info:
        aoi_builder.build_from_request(build_request)

    assert isinstance(root_cause(exc_info.value), DataCRSError)


def test_builder_rejects_overlaps_when_not_allowed(
    aoi_builder,
    make_aoi_build_request,
):
    build_request = make_aoi_build_request(
        spec=preserve_features_request(allow_overlaps=False),
        raw_gdf=overlapping_polygons_gdf(),
    )

    with pytest.raises(AOIBuildError) as exc_info:
        aoi_builder.build_from_request(build_request)

    assert isinstance(root_cause(exc_info.value), SpatialGeometryError)