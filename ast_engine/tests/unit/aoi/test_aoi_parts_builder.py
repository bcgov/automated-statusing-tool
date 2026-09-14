from __future__ import annotations

import geopandas as gpd
import pandas as pd
import pytest
import shapely
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
    AOIPartBuildError,
    DataCRSError,
    SpatialDataError,
    SpatialGeometryError,
)
from ast_engine.core.aoi.models import AOIPart
from ast_engine.core.aoi.parts_builder import AOIPartBuilder
from ast_engine.tests.helpers.aoi_geometry import aoi_gdf, rect


pytestmark = pytest.mark.unit

M_SUPPORTED = (
    hasattr(shapely, "has_m")
    and getattr(shapely, "geos_version", (0, 0, 0)) >= (3, 12, 0)
)


@pytest.fixture
def part_builder() -> AOIPartBuilder:
    return AOIPartBuilder()


def _make_part_factory_raise(monkeypatch, failure: Exception) -> None:
    """Inject only a factory failure, preserving the normal input checks/explode."""
    def fail(cls, **kwargs):
        raise failure

    monkeypatch.setattr(AOIPart, "from_gdf", classmethod(fail))


# Part identity, geometry, and measurements


def test_single_polygon_has_expected_identity_geometry_and_properties(part_builder):
    polygon = rect(100, 200, 300, 350)  # 200 m x 150 m = 3 ha.

    parts = part_builder.build_parts(aoi_id="watershed_17", gdf=aoi_gdf([polygon]))

    assert isinstance(parts, tuple)
    assert len(parts) == 1
    part = parts[0]
    assert isinstance(part, AOIPart)
    assert part.part_id == "watershed_17_part_0001"
    assert part.parent_aoi_id == "watershed_17"
    assert part.part_index == 1
    assert part.geom_type == "Polygon"
    assert part.geometry.equals(polygon)
    assert part.geometry.is_valid
    assert part.bounds == pytest.approx((100, 200, 300, 350))
    assert part.area_ha == pytest.approx(3.0)
    assert part.vertex_count == 5
    assert part.has_z is False
    assert part.has_m is False
    assert len(part.gdf) == 1
    assert part.gdf.index.tolist() == [0]
    assert part.crs.to_epsg() == 3005


def test_mixed_polygon_and_multipolygon_rows_get_sequential_parts(part_builder):
    # Deliberately put the larger polygon first; part order follows the input.
    first = rect(300, 0, 500, 100)  # 2 ha.
    second = rect(0, 0, 100, 100)  # 1 ha.
    third = rect(600, 0, 900, 100)  # 3 ha.
    source = aoi_gdf(
        [MultiPolygon([first, second]), third],
        SourceId=[21, 7],
        Name=["multipart", "single"],
    )

    parts = part_builder.build_parts(aoi_id="test_aoi", gdf=source)

    assert len(parts) == 3
    assert [part.part_index for part in parts] == [1, 2, 3]
    assert [part.part_id for part in parts] == [
        "test_aoi_part_0001", "test_aoi_part_0002", "test_aoi_part_0003"
    ]
    assert [part.parent_aoi_id for part in parts] == ["test_aoi"] * 3
    assert [part.area_ha for part in parts] == pytest.approx([2.0, 1.0, 3.0])
    assert [part.gdf["SourceId"].iloc[0] for part in parts] == [21, 21, 7]
    assert [part.gdf["Name"].iloc[0] for part in parts] == ["multipart", "multipart", "single"]

    for part, expected in zip(parts, [first, second, third], strict=True):
        assert isinstance(part, AOIPart)
        assert isinstance(part.geometry, Polygon)
        assert part.geom_type == "Polygon"
        assert part.geometry.equals(expected)
        assert len(part.gdf) == 1
        assert part.gdf.index.tolist() == [0]
        assert part.crs == source.crs


def test_holes_stay_with_their_polygon_and_metrics_are_computed_per_part(part_builder):
    holed = Polygon(
        [(0, 0), (300, 0), (300, 200), (0, 200)],
        holes=[
            [(25, 25), (125, 25), (125, 125), (25, 125)],
            [(200, 50), (250, 50), (250, 100), (200, 100)],
        ],
    )
    solid = rect(400, 0, 500, 100)

    parts = part_builder.build_parts(
        aoi_id="holes", gdf=aoi_gdf([MultiPolygon([holed, solid])])
    )

    assert len(parts) == 2
    assert parts[0].geometry.equals(holed)
    assert len(parts[0].geometry.interiors) == 2
    assert parts[0].area_ha == pytest.approx(4.75)  # 6 - 1 - 0.25 ha.
    assert parts[0].vertex_count == 15  # Three closed rings, five coordinates each.
    assert parts[0].bounds == pytest.approx((0, 0, 300, 200))

    assert parts[1].geometry.equals(solid)
    assert len(parts[1].geometry.interiors) == 0
    assert parts[1].area_ha == pytest.approx(1.0)
    assert parts[1].vertex_count == 5
    assert parts[1].bounds == pytest.approx((400, 0, 500, 100))


def test_touching_features_stay_as_separate_parts(part_builder):
    first = rect(0, 0, 100, 100)
    second = rect(100, 0, 200, 100)

    parts = part_builder.build_parts(
        aoi_id="touching", gdf=aoi_gdf([first, second], SourceId=["A", "B"])
    )

    assert len(parts) == 2
    assert parts[0].geometry.equals(first)
    assert parts[1].geometry.equals(second)
    assert [part.gdf["SourceId"].iloc[0] for part in parts] == ["A", "B"]
    assert sum(part.area_ha for part in parts) == pytest.approx(2.0)


def test_overlapping_valid_features_are_preserved_without_dissolving(part_builder):
    """Overlap policy was already decided by the normalizer; retain both features."""
    first = rect(0, 0, 100, 100)
    second = rect(50, 0, 150, 100)

    parts = part_builder.build_parts(
        aoi_id="overlap", gdf=aoi_gdf([first, second], SourceId=["A", "B"])
    )

    assert len(parts) == 2
    assert parts[0].geometry.equals(first)
    assert parts[1].geometry.equals(second)
    assert sum(part.area_ha for part in parts) == pytest.approx(2.0)
    assert parts[0].geometry.union(parts[1].geometry).area == pytest.approx(15_000.0)


# Source indexes, column names, and attribute preservation


@pytest.mark.parametrize(
    "make_index",
    [
        pytest.param(lambda: pd.Index([30, 10], name="source_row"), id="nonconsecutive"),
        pytest.param(lambda: pd.Index(["north", "south"]), id="text-labels"),
        pytest.param(lambda: pd.Index(["same", "same"]), id="duplicate-labels"),
        pytest.param(
            lambda: pd.MultiIndex.from_tuples(
                [("batch_B", 9), ("batch_A", 2)], names=["batch", "source_row"]
            ),
            id="multiindex",
        ),
    ],
)
def test_source_index_does_not_control_part_ids_or_lose_rows(part_builder, make_index):
    first = rect(0, 0, 100, 100)
    second = rect(200, 0, 300, 100)
    third = rect(400, 0, 500, 100)
    source = aoi_gdf(
        [MultiPolygon([first, second]), third], SourceId=["multi", "single"]
    )
    source.index = make_index()
    original_index = source.index.copy()

    parts = part_builder.build_parts(aoi_id="indexed", gdf=source)

    assert len(parts) == 3
    assert [part.part_index for part in parts] == [1, 2, 3]
    assert [part.part_id for part in parts] == [
        "indexed_part_0001", "indexed_part_0002", "indexed_part_0003"
    ]
    assert [part.gdf["SourceId"].iloc[0] for part in parts] == ["multi", "multi", "single"]
    for part, expected in zip(parts, [first, second, third], strict=True):
        assert part.geometry.equals(expected)
        assert part.gdf.index.tolist() == [0]
    assert source.index.equals(original_index)


@pytest.mark.parametrize("geometry_column", ["shape", "boundary geometry"])
def test_custom_active_geometry_column_survives_splitting(part_builder, geometry_column):
    first = rect(0, 0, 100, 100)
    second = rect(200, 0, 300, 100)
    source = aoi_gdf(
        [MultiPolygon([first, second])], Name=["custom geometry"]
    ).rename_geometry(geometry_column)

    parts = part_builder.build_parts(aoi_id="custom", gdf=source)

    assert len(parts) == 2
    for part, expected in zip(parts, [first, second], strict=True):
        assert part.gdf.geometry.name == geometry_column
        assert part.geometry.equals(expected)
        assert part.gdf["Name"].iloc[0] == "custom geometry"
        assert part.crs == source.crs


def test_uses_active_geometry_when_an_unrelated_geometry_column_also_exists(part_builder):
    first = rect(0, 0, 100, 100)
    second = rect(200, 0, 300, 100)
    source = aoi_gdf([MultiPolygon([first, second])]).rename_geometry("shape")
    source["geometry"] = "source description, not the active geometry"

    parts = part_builder.build_parts(aoi_id="active", gdf=source)

    assert len(parts) == 2
    for part, expected in zip(parts, [first, second], strict=True):
        assert part.gdf.geometry.name == "shape"
        assert part.geometry.equals(expected)
        assert part.gdf["geometry"].iloc[0] == "source description, not the active geometry"


@pytest.mark.parametrize(
    "missing",
    [
        pytest.param(None, id="none"),
        pytest.param(float("nan"), id="nan"),
        pytest.param(pd.NA, id="pd-NA"),
    ],
)
def test_missing_group_keys_are_retained_on_all_exploded_parts(part_builder, missing):
    """A normalized null-key group can be a MultiPolygon; every piece must survive."""
    first = rect(0, 0, 100, 100)
    second = rect(200, 0, 300, 100)
    named = rect(400, 0, 500, 100)
    source = aoi_gdf(
        [MultiPolygon([first, second]), named],
        region=["North", "South"],
        group_id=[missing, "A"],
    )

    parts = part_builder.build_parts(aoi_id="null_group", gdf=source)

    assert len(parts) == 3
    assert [part.gdf["region"].iloc[0] for part in parts] == ["North", "North", "South"]
    assert pd.isna(parts[0].gdf["group_id"].iloc[0])
    assert pd.isna(parts[1].gdf["group_id"].iloc[0])
    assert parts[2].gdf["group_id"].iloc[0] == "A"
    for part, expected in zip(parts, [first, second, named], strict=True):
        assert part.geometry.equals(expected)
    assert len({part.part_id for part in parts}) == 3


def test_nullable_and_categorical_attribute_types_are_preserved(part_builder):
    source = aoi_gdf(
        [MultiPolygon([rect(0, 0, 100, 100), rect(200, 0, 300, 100)])]
    )
    source["Count"] = pd.Series([pd.NA], dtype="Int64")
    source["Enabled"] = pd.Series([True], dtype="boolean")
    source["Category"] = pd.Categorical(["A"], categories=["A", "B"])

    parts = part_builder.build_parts(aoi_id="attributes", gdf=source)

    assert len(parts) == 2
    for part in parts:
        for column in ["Count", "Enabled", "Category"]:
            assert part.gdf[column].dtype == source[column].dtype
        assert pd.isna(part.gdf["Count"].iloc[0])
        assert bool(part.gdf["Enabled"].iloc[0]) is True
        assert part.gdf["Category"].iloc[0] == "A"


def test_source_part_columns_are_preserved_separately_from_generated_identity(part_builder):
    source = aoi_gdf(
        [MultiPolygon([rect(0, 0, 100, 100), rect(200, 0, 300, 100)])],
        part_id=["source_record"],
        part_index=[42],
    )

    parts = part_builder.build_parts(aoi_id="new_aoi", gdf=source)

    assert len(parts) == 2
    assert [part.part_id for part in parts] == ["new_aoi_part_0001", "new_aoi_part_0002"]
    assert [part.part_index for part in parts] == [1, 2]
    assert [part.gdf["part_id"].iloc[0] for part in parts] == ["source_record"] * 2
    assert [part.gdf["part_index"].iloc[0] for part in parts] == [42, 42]


# CRS and coordinate dimensions


@pytest.mark.parametrize(
    "crs",
    [
        pytest.param("EPSG:3005", id="bc-albers"),
        pytest.param("EPSG:26910", id="nad83-utm-10"),
        pytest.param(
            "+proj=aeqd +lat_0=54 +lon_0=-125 +datum=WGS84 +units=m +no_defs +type=crs",
            id="local-projected-crs",
        ),
    ],
)
def test_preserves_projected_crs_and_coordinates_without_reprojecting(part_builder, crs):
    polygon = rect(100, 200, 300, 350)
    source = aoi_gdf([polygon], crs=crs)

    parts = part_builder.build_parts(aoi_id="crs", gdf=source)

    assert len(parts) == 1
    part = parts[0]
    assert part.crs == CRS.from_user_input(crs)
    assert part.gdf.crs == source.crs
    assert list(part.geometry.exterior.coords) == list(polygon.exterior.coords)
    assert part.bounds == pytest.approx((100, 200, 300, 350))
    assert part.area_ha == pytest.approx(3.0)


def test_z_values_are_preserved_and_dimension_flags_are_per_part(part_builder):
    flat = rect(200, 0, 300, 100)
    raised = Polygon(
        [(0, 0, 10), (100, 0, 20), (100, 100, 30), (0, 100, 40), (0, 0, 10)]
    )

    parts = part_builder.build_parts(aoi_id="heights", gdf=aoi_gdf([flat, raised]))

    assert len(parts) == 2
    assert [part.has_z for part in parts] == [False, True]
    assert [part.has_m for part in parts] == [False, False]
    assert list(parts[1].geometry.exterior.coords) == list(raised.exterior.coords)
    # Areas use the XY footprint in metres, regardless of varying Z values.
    assert [part.area_ha for part in parts] == pytest.approx([1.0, 1.0])
    assert [part.vertex_count for part in parts] == [5, 5]


@pytest.mark.skipif(
    not M_SUPPORTED, reason="M coordinates require Shapely 2.1+ and GEOS 3.12+"
)
@pytest.mark.parametrize(
    ("wkt", "expected_has_z"),
    [
        pytest.param(
            "POLYGON M ((0 0 7, 100 0 8, 100 100 9, 0 100 10, 0 0 7))",
            False,
            id="XYM",
        ),
        pytest.param(
            "POLYGON ZM ((0 0 10 7, 100 0 20 8, 100 100 30 9, "
            "0 100 40 10, 0 0 10 7))",
            True,
            id="XYZM",
        ),
    ],
)
def test_m_values_survive_and_m_flags_are_computed_per_part(part_builder, wkt, expected_has_z):
    # Parse inside the test so unsupported installations can skip before parsing M.
    measured = shapely.from_wkt(wkt)
    flat = rect(200, 0, 300, 100)

    parts = part_builder.build_parts(aoi_id="measures", gdf=aoi_gdf([flat, measured]))

    assert len(parts) == 2
    assert [part.has_m for part in parts] == [False, True]
    assert [part.has_z for part in parts] == [False, expected_has_z]
    assert list(parts[1].geometry.exterior.coords) == list(measured.exterior.coords)
    assert parts[1].area_ha == pytest.approx(1.0)
    assert parts[1].vertex_count == 5


# Source ownership and repeated calls


def test_building_and_editing_one_part_leave_source_and_sibling_unchanged(part_builder):
    source = aoi_gdf(
        [MultiPolygon([rect(0, 0, 100, 100), rect(200, 0, 300, 100)])],
        Name=["Original"],
        SourceId=[12],
    ).rename_geometry("shape")
    source.index = pd.Index([50], name="source_row")
    source_before = source.copy(deep=True)

    parts = part_builder.build_parts(aoi_id="isolation", gdf=source)

    assert len(parts) == 2
    assert_geodataframe_equal(source, source_before)
    sibling_before = parts[1].gdf.copy(deep=True)

    # Deliberately edit one result frame to detect shared data. Derived AOIPart
    # metadata remains a snapshot; this test does not expect it to recompute.
    parts[0].gdf.loc[0, "Name"] = "Changed"
    parts[0].gdf.loc[0, "shape"] = rect(900, 0, 1_000, 100)
    parts[0].gdf["output_only"] = True

    assert_geodataframe_equal(source, source_before)
    assert_geodataframe_equal(parts[1].gdf, sibling_before)


def test_repeated_calls_restart_numbering_and_return_fresh_part_frames(part_builder):
    source = aoi_gdf(
        [MultiPolygon([rect(0, 0, 100, 100), rect(200, 0, 300, 100)])]
    )

    first = part_builder.build_parts(aoi_id="first", gdf=source)
    second = part_builder.build_parts(
        aoi_id="second", gdf=aoi_gdf([rect(400, 0, 500, 100)])
    )
    repeat = part_builder.build_parts(aoi_id="first", gdf=source)

    assert len(first) == len(repeat) == 2
    assert len(second) == 1
    assert [part.part_id for part in first] == ["first_part_0001", "first_part_0002"]
    assert second[0].part_id == "second_part_0001"
    assert second[0].part_index == 1
    assert second[0].parent_aoi_id == "second"
    assert [part.part_id for part in repeat] == [part.part_id for part in first]
    for original, rebuilt in zip(first, repeat, strict=True):
        assert rebuilt is not original
        assert rebuilt.gdf is not original.gdf
        assert_geodataframe_equal(rebuilt.gdf, original.gdf)


# Input validation: normalized input must already be usable and polygonal


@pytest.mark.parametrize(
    "make_input",
    [
        pytest.param(lambda: None, id="none"),
        pytest.param(lambda: pd.DataFrame({"Name": ["plain dataframe"]}), id="wrong-type"),
        pytest.param(lambda: aoi_gdf([]), id="empty-geodataframe"),
    ],
)
def test_rejects_missing_wrong_type_and_empty_input(part_builder, make_input):
    with pytest.raises(AOIPartBuildError, match="bad_input") as exc_info:
        part_builder.build_parts(aoi_id="bad_input", gdf=make_input())

    assert isinstance(exc_info.value.__cause__, SpatialDataError)


@pytest.mark.parametrize(
    ("crs", "polygon"),
    [
        pytest.param(None, rect(0, 0, 100, 100), id="missing-crs"),
        pytest.param("EPSG:4326", rect(-123.2, 49.1, -123.1, 49.2), id="geographic-crs"),
    ],
)
def test_rejects_missing_or_geographic_crs_with_crs_cause(part_builder, crs, polygon):
    with pytest.raises(AOIPartBuildError, match="bad_crs") as exc_info:
        part_builder.build_parts(aoi_id="bad_crs", gdf=aoi_gdf([polygon], crs=crs))

    assert isinstance(exc_info.value.__cause__, DataCRSError)


def test_missing_active_geometry_is_wrapped_as_geometry_error(part_builder):
    """Regression for the shared check_gdf ordering of geometry and CRS checks."""
    source = gpd.GeoDataFrame({"Name": ["no active geometry"]})

    with pytest.raises(AOIPartBuildError, match="no_geometry") as exc_info:
        part_builder.build_parts(aoi_id="no_geometry", gdf=source)

    # The geometry error may itself chain a GeoPandas AttributeError, so inspect
    # the immediate cause instead of requiring a particular deepest exception.
    assert isinstance(exc_info.value.__cause__, SpatialGeometryError)


@pytest.mark.parametrize(
    "bad_geometry",
    [
        pytest.param(None, id="null-geometry"),
        pytest.param(Polygon(), id="empty-polygon"),
        pytest.param(MultiPolygon(), id="empty-multipolygon"),
        pytest.param(Point(500, 500), id="point"),
        pytest.param(LineString([(500, 0), (600, 0)]), id="line"),
        pytest.param(MultiPoint([(500, 0), (600, 0)]), id="multipoint"),
        pytest.param(
            MultiLineString([[(500, 0), (600, 0)], [(700, 0), (800, 0)]]),
            id="multiline",
        ),
        pytest.param(
            GeometryCollection([rect(500, 0, 600, 100)]),
            id="collection-containing-polygon",
        ),
        pytest.param(
            Polygon([(500, 0), (600, 100), (500, 100), (600, 0), (500, 0)]),
            id="self-intersecting-polygon",
        ),
        pytest.param(
            MultiPolygon([rect(500, 0, 600, 100), rect(550, 0, 650, 100)]),
            id="invalid-overlapping-multipolygon",
        ),
    ],
)
def test_rejects_bad_geometry_instead_of_silently_dropping_or_repairing_it(
    part_builder, bad_geometry
):
    # Including a good row ensures that silently discarding the bad row fails
    # this test. The part builder must reject the invalid input as a whole.
    source = aoi_gdf(
        [rect(0, 0, 100, 100), bad_geometry], Name=["valid", "bad"]
    )
    before = source.copy(deep=True)

    with pytest.raises(AOIPartBuildError, match="bad_geometry") as exc_info:
        part_builder.build_parts(aoi_id="bad_geometry", gdf=source)

    assert isinstance(exc_info.value.__cause__, SpatialGeometryError)
    assert_geodataframe_equal(source, before)


# Exception behavior after initial input validation


def test_wraps_a_domain_error_from_the_part_factory(part_builder, monkeypatch):
    failure = SpatialGeometryError("part factory geometry failure")
    _make_part_factory_raise(monkeypatch, failure)

    with pytest.raises(AOIPartBuildError, match="factory_aoi") as exc_info:
        part_builder.build_parts(
            aoi_id="factory_aoi", gdf=aoi_gdf([rect(0, 0, 100, 100)])
        )

    assert exc_info.value is not failure
    assert exc_info.value.__cause__ is failure


def test_existing_part_build_error_is_propagated_unchanged(part_builder, monkeypatch):
    failure = AOIPartBuildError("already a part build error")
    _make_part_factory_raise(monkeypatch, failure)

    with pytest.raises(AOIPartBuildError) as exc_info:
        part_builder.build_parts(
            aoi_id="factory_aoi", gdf=aoi_gdf([rect(0, 0, 100, 100)])
        )

    assert exc_info.value is failure


def test_unexpected_factory_error_bubbles_up_unchanged(part_builder, monkeypatch):
    failure = RuntimeError("unexpected part factory failure")
    _make_part_factory_raise(monkeypatch, failure)

    with pytest.raises(RuntimeError) as exc_info:
        part_builder.build_parts(
            aoi_id="factory_aoi", gdf=aoi_gdf([rect(0, 0, 100, 100)])
        )

    assert exc_info.value is failure