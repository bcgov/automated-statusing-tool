from __future__ import annotations

import pytest
from geopandas.testing import assert_geodataframe_equal
from shapely.geometry import Point, Polygon, box

from ast_engine.tests.helpers.aoi_geometry import (
    aoi_gdf,
    bowtie,
    line_point_collection,
    missing_crs_gdf,
    multipolygon_gdf,
    overlapping_polygons_gdf,
    polygon_line_collection,
    polygon_point_collection,
    squares,
    squares_gdf,
    bowtie_gdf,
)

pytestmark = pytest.mark.unit


def test_overlapping_polygons_gdf_contains_overlapping_features():
    """Create a GeoDataFrame with two overlapping polygons and verify that they overlap."""

    gdf = overlapping_polygons_gdf()

    assert len(gdf) == 2
    assert (
        gdf.geometry.iloc[0]
        .intersection(gdf.geometry.iloc[1])
        .area
    ) == pytest.approx(400.0)


def test_bowtie_gdf_contains_invalid_geometry():
    """Create a GeoDataFrame with a self-intersecting polygon and verify that it is invalid."""
    gdf = bowtie_gdf()

    assert len(gdf) == 1
    assert not gdf.geometry.iloc[0].is_valid


def test_missing_crs_gdf_has_no_crs():
    """Create a GeoDataFrame with no CRS and verify that it has no CRS."""
    gdf = missing_crs_gdf()

    assert gdf.crs is None


def test_multipolygon_gdf_contains_multipart_geometry():
    """Create a GeoDataFrame with a multipolygon geometry and verify that it is a MultiPolygon."""
    gdf = multipolygon_gdf()

    geom = gdf.geometry.iloc[0]

    assert len(gdf) == 1
    assert geom.is_valid
    assert geom.geom_type == "MultiPolygon"
    assert len(geom.geoms) == 2
    assert sorted(part.area for part in geom.geoms) == pytest.approx(
        [10_000, 10_000]
    )
    assert geom.geoms[0].disjoint(geom.geoms[1])


def test_aoi_gdf_does_not_add_unrequested_attributes():
    """Missing-ID tests must receive data that actually has no ID column."""
    source = aoi_gdf([box(0, 0, 100, 100)])

    assert list(source.columns) == ["geometry"]
    assert source.geometry.name == "geometry"
    assert source.crs.to_epsg() == 3005


@pytest.mark.parametrize(
    "crs",
    [
        pytest.param("EPSG:3005", id="projected"),
        pytest.param("EPSG:4326", id="geographic"),
        pytest.param(None, id="missing-crs"),
    ],
)
def test_aoi_gdf_preserves_supplied_data_and_crs(crs):
    """Construction must preserve feature order and caller-supplied values."""
    geometries = [
        box(0, 0, 1, 1),
        box(2, 0, 3, 1),
    ]

    source = aoi_gdf(
        geometries,
        crs=crs,
        Id=[20, 10],
        Name=["first", "second"],
    )

    assert len(source) == 2
    assert set(source.columns) == {"Id", "Name", "geometry"}
    assert source["Id"].tolist() == [20, 10]
    assert source["Name"].tolist() == ["first", "second"]

    # Assigning a CRS must not change the supplied coordinates.
    assert source.geometry.iloc[0].bounds == pytest.approx((0, 0, 1, 1))
    assert source.geometry.iloc[1].bounds == pytest.approx((2, 0, 3, 1))

    if crs is None:
        assert source.crs is None
    else:
        assert str(source.crs) == crs


def test_aoi_gdf_preserves_unusable_geometry_for_negative_tests():
    """The helper must not perform the normalizer's cleanup."""
    invalid = bowtie()

    source = aoi_gdf(
        [
            None,
            Polygon(),
            Point(5, 5),
            invalid,
        ],
        case=["null", "empty", "point", "invalid"],
    )

    assert len(source) == 4
    assert source["case"].tolist() == [
        "null",
        "empty",
        "point",
        "invalid",
    ]
    assert source.geometry.iloc[0] is None
    assert source.geometry.iloc[1].is_empty
    assert source.geometry.iloc[2].geom_type == "Point"
    assert not source.geometry.iloc[3].is_valid
    assert source.geometry.iloc[3].wkb == invalid.wkb


def test_aoi_gdf_can_create_an_empty_dataset():
    """Empty-result tests need a usable empty frame with an active geometry."""
    source = aoi_gdf([])

    assert source.empty
    assert source.geometry.name == "geometry"
    assert source.crs.to_epsg() == 3005


@pytest.mark.parametrize(
    "make_gdf",
    [
        pytest.param(overlapping_polygons_gdf, id="overlapping"),
        pytest.param(multipolygon_gdf, id="multipart"),
        pytest.param(missing_crs_gdf, id="missing-crs"),
    ],
)
def test_scenario_factories_return_independent_frames(make_gdf):
    """Changing one test's data must not change another test's data."""
    first = make_gdf()
    second = make_gdf()
    expected = second.copy()

    first.at[0, "group_id"] = "changed"
    first.at[0, first.geometry.name] = box(500, 500, 600, 600)
    first["extra"] = "only on the first frame"

    assert_geodataframe_equal(second, expected)

    # Later calls must also start with the original scenario.
    assert_geodataframe_equal(make_gdf(), expected)


def test_separated_squares_have_known_dimensions_and_spacing():
    """Three 100 m squares start at the requested origin, with 50 m gaps."""
    geometries = squares(
        count=3,
        size=100,
        xmin=10,
        ymin=20,
        overlap=False,
    )

    assert len(geometries) == 3
    assert [geom.area for geom in geometries] == pytest.approx(
        [10_000, 10_000, 10_000]
    )

    assert geometries[0].bounds == pytest.approx((10, 20, 110, 120))
    assert geometries[1].bounds == pytest.approx((160, 20, 260, 120))
    assert geometries[2].bounds == pytest.approx((310, 20, 410, 120))

    assert geometries[0].distance(geometries[1]) == pytest.approx(50)
    assert geometries[1].distance(geometries[2]) == pytest.approx(50)


def test_squares_gdf_preserves_options_and_creates_known_overlap():
    """Two 100 m squares overlap by 50 m × 100 m."""
    source = squares_gdf(
        count=2,
        size=100,
        overlap=True,
        xmin=10,
        ymin=20,
        crs=None,
        group_id=["A", "B"],
    )

    assert len(source) == 2
    assert source.crs is None
    assert source["group_id"].tolist() == ["A", "B"]

    first, second = source.geometry

    assert first.bounds == pytest.approx((10, 20, 110, 120))
    assert second.bounds == pytest.approx((60, 20, 160, 120))
    assert first.intersection(second).area == pytest.approx(5_000)


@pytest.mark.parametrize(
    ("count", "size", "message"),
    [
        pytest.param(0, 100, "count", id="zero-count"),
        pytest.param(-1, 100, "count", id="negative-count"),
        pytest.param(2, 0, "size", id="zero-size"),
        pytest.param(2, -100, "size", id="negative-size"),
    ],
)
def test_squares_rejects_invalid_dimensions(count, size, message):
    with pytest.raises(ValueError, match=message):
        squares(count=count, size=size)


@pytest.mark.parametrize(
    "values",
    [
        pytest.param(["A"], id="too-few"),
        pytest.param(["A", "B", "C"], id="too-many"),
    ],
)
def test_squares_gdf_rejects_mismatched_attribute_lengths(values):
    with pytest.raises(ValueError, match="group_id"):
        squares_gdf(
            count=2,
            size=100,
            group_id=values,
        )


@pytest.mark.parametrize(
    ("make_geometry", "expected_types", "expected_area"),
    [
        pytest.param(
            polygon_line_collection,
            ("LineString", "Polygon"),
            10_000,
            id="polygon-and-line",
        ),
        pytest.param(
            polygon_point_collection,
            ("Point", "Polygon"),
            10_000,
            id="polygon-and-point",
        ),
        pytest.param(
            line_point_collection,
            ("LineString", "Point"),
            0,
            id="no-polygon",
        ),
    ],
)
def test_collection_helpers_contain_the_expected_components(
    make_geometry,
    expected_types,
    expected_area,
):
    geometry = make_geometry()

    assert geometry.geom_type == "GeometryCollection"
    assert tuple(sorted(part.geom_type for part in geometry.geoms)) == (
        expected_types
    )
    assert sum(part.area for part in geometry.geoms) == pytest.approx(
        expected_area
    )