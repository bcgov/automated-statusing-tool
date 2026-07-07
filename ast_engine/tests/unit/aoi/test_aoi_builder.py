# tests/unit/aoi/test_aoi_builder.py

from __future__ import annotations

import pytest

from tests.helpers.aoi_geometry import (
    overlapping_polygons_gdf,
    multipolygon_gdf,
    missing_crs_gdf
)
from tests.helpers.aoi_requests import full_union_request

pytestmark = pytest.mark.unit


def test_builder_handles_overlapping_polygons_with_full_union(
    aoi_builder,
    make_aoi_build_request,
):
    build_request = make_aoi_build_request(
        spec=full_union_request(),
        raw_gdf=overlapping_polygons_gdf(),
    )

    result = aoi_builder.build_from_request(build_request)

    assert result.is_valid
    assert result.aoi is not None
    assert len(result.aoi.parts) >= 1



def test_builder_splits_multipolygon_into_parts(
    aoi_builder,
    make_aoi_build_request,
):
    build_request = make_aoi_build_request(
        spec=full_union_request(),
        raw_gdf=multipolygon_gdf(),
    )

    result = aoi_builder.build_from_request(build_request)

    assert result.is_valid
    assert result.aoi is not None
    assert len(result.aoi.parts) == 2


def test_builder_rejects_missing_crs(
    aoi_builder,
    make_aoi_build_request,
):
    build_request = make_aoi_build_request(
        spec=full_union_request(),
        raw_gdf=missing_crs_gdf(),
    )

    with pytest.raises(AOIBuildError):
        aoi_builder.build_from_request(build_request)