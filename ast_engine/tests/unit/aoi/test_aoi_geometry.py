from __future__ import annotations

import pytest

from ast_engine.tests.helpers.aoi_geometry import (
    bowtie_gdf,
    missing_crs_gdf,
    multipolygon_gdf,
    overlapping_polygons_gdf,
)

pytestmark = pytest.mark.unit


def test_overlapping_polygons_gdf_contains_overlapping_features():
    gdf = overlapping_polygons_gdf()

    assert len(gdf) == 2
    assert gdf.geometry.iloc[0].intersects(gdf.geometry.iloc[1])


def test_bowtie_gdf_contains_invalid_geometry():
    gdf = bowtie_gdf()

    assert len(gdf) == 1
    assert not gdf.geometry.iloc[0].is_valid


def test_missing_crs_gdf_has_no_crs():
    gdf = missing_crs_gdf()

    assert gdf.crs is None


def test_multipolygon_gdf_contains_multipart_geometry():
    gdf = multipolygon_gdf()

    geom = gdf.geometry.iloc[0]

    assert geom.geom_type == "MultiPolygon"
    assert len(geom.geoms) == 2