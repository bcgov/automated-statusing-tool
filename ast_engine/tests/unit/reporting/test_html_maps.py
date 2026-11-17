"""
Tests for the HTML map generator.

The maps are built from small layers made in memory and saved as GeoPackages,
the form the generator reads a run's spatial output in. The tests read the
written pages as text: what a browser would be given to draw.
"""

from datetime import date
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import LineString, Point, box

from ast_engine.reporting import html_maps
from ast_engine.reporting.html_maps import (
    LAYER_PALETTE,
    MAX_LEGEND_VALUES,
    OVERVIEW_MAP_NAME,
    SINGLE_LAYER_COLOUR,
    MapLayer,
    generate_html_maps,
)

pytestmark = pytest.mark.unit

MAP_DATE = date(2026, 3, 31)


@pytest.fixture
def aoi() -> gpd.GeoDataFrame:
    """A 1 km square in BC Albers."""
    return gpd.GeoDataFrame(geometry=[box(1_200_000, 460_000, 1_201_000, 461_000)], crs="EPSG:3005")


def _save(tmp_path: Path, name: str, gdf: gpd.GeoDataFrame) -> Path:
    path = tmp_path / f"{name}.gpkg"
    gdf.to_file(path, driver="GPKG")
    return path


def _parks(tmp_path: Path, name: str = "parks") -> Path:
    """Two polygons with a report field, as an overlay run would save them."""
    gdf = gpd.GeoDataFrame(
        {
            "OBJECTID": [1, 2],
            "PARK_CLASS": ["Class A", "Class B"],
            "overlap_area_m2": [100.0, 200.0],
        },
        geometry=[box(1_200_100, 460_100, 1_200_400, 460_400), box(1_200_500, 460_500, 1_200_900, 460_900)],
        crs="EPSG:3005",
    )
    return _save(tmp_path, name, gdf)


def _layer(path: Path, **overrides) -> MapLayer:
    values = {
        "title": "Parks",
        "group": "provincial",
        "datasource": "WHSE_PARKS.PARKS_SVW",
        "paths": (path,),
        "summarize_fields": ("PARK_CLASS",),
        "key": "parks-id",
    }
    values.update(overrides)
    return MapLayer(**values)


def _generate(aoi, layers, tmp_path):
    return generate_html_maps(aoi=aoi, layers=layers, out_dir=tmp_path / "maps", map_date=MAP_DATE)


# --- What is written ---------------------------------------------------------
def test_writes_the_overview_first_then_one_map_per_dataset(aoi, tmp_path):
    outputs = _generate(aoi, [_layer(_parks(tmp_path))], tmp_path)

    assert [output.name for output in outputs] == [OVERVIEW_MAP_NAME, "provincial__Parks"]
    assert [output.title for output in outputs] == ["Overview Map - All Overlaps", "Parks"]
    assert all(output.path.is_file() for output in outputs)
    # Each dataset's map carries its layer's key back; the overview has none.
    assert [output.key for output in outputs] == [None, "parks-id"]
    assert outputs[1].path == tmp_path / "maps" / "provincial__Parks.html"


def test_a_dataset_with_no_features_gets_no_map(aoi, tmp_path):
    empty = _save(tmp_path, "empty", gpd.GeoDataFrame({"A": []}, geometry=[], crs="EPSG:3005"))
    layers = [
        _layer(empty, title="Nothing here"),
        _layer(tmp_path / "never_written.gpkg", title="No file"),
        _layer(_parks(tmp_path)),
    ]

    outputs = _generate(aoi, layers, tmp_path)

    assert [output.title for output in outputs] == ["Overview Map - All Overlaps", "Parks"]


def test_nothing_is_written_when_no_dataset_has_features(aoi, tmp_path):
    outputs = _generate(aoi, [_layer(tmp_path / "never_written.gpkg")], tmp_path)

    assert outputs == []
    assert list((tmp_path / "maps").glob("*.html")) == []


def test_one_dataset_failing_does_not_stop_the_others(aoi, tmp_path, monkeypatch):
    real_prepare = html_maps._prepare_layer

    def prepare(layer):
        if layer.title == "Broken":
            raise RuntimeError("cannot draw this one")
        return real_prepare(layer)

    monkeypatch.setattr(html_maps, "_prepare_layer", prepare)
    layers = [_layer(_parks(tmp_path, "broken"), title="Broken"), _layer(_parks(tmp_path))]

    outputs = _generate(aoi, layers, tmp_path)

    assert [output.title for output in outputs] == ["Overview Map - All Overlaps", "Parks"]


def test_two_datasets_with_the_same_name_keep_separate_maps(aoi, tmp_path):
    """Tab 1 repeats datasets from the provincial registry under the same name;
    two names can also come down to the same file name once cleaned."""
    layers = [
        _layer(_parks(tmp_path, "a"), group="provincial"),
        _layer(_parks(tmp_path, "b"), group="tab1"),
        _layer(_parks(tmp_path, "c"), group="tab1", title="Parks!"),
        _layer(_parks(tmp_path, "d"), group="tab1", title="Parks?"),
    ]

    names = [output.name for output in _generate(aoi, layers, tmp_path)]

    assert names == [OVERVIEW_MAP_NAME, "provincial__Parks", "tab1__Parks", "tab1__Parks_2", "tab1__Parks_3"]


def test_map_names_are_safe_for_a_url(aoi, tmp_path):
    layer = _layer(_parks(tmp_path), title="Parks / Protected (2026)", group="one status: common")

    name = _generate(aoi, [layer], tmp_path)[1].name

    assert name == "one_status_common__Parks_Protected_2026"


# --- What a dataset's map shows ----------------------------------------------
def test_map_carries_the_title_the_notice_and_the_date(aoi, tmp_path):
    page = _generate(aoi, [_layer(_parks(tmp_path))], tmp_path)[1].path.read_text(encoding="utf-8")

    assert "<title>Parks</title>" in page
    assert "Water, Land, and Resource Stewardship | Front Counter BC" in page
    assert "© 2026 Government of British Columbia | INTERNAL GOVERNMENT USE ONLY" in page
    assert "Map Date: March 31, 2026" in page
    assert 'src="data:image/jpeg;base64,' in page


def test_features_are_coloured_by_the_first_report_field(aoi, tmp_path):
    """One palette colour per value, in order over the sorted values, with a
    legend row for each - so the same data always makes the same map."""
    page = _generate(aoi, [_layer(_parks(tmp_path))], tmp_path)[1].path.read_text(encoding="utf-8")

    assert LAYER_PALETTE[0] in page and LAYER_PALETTE[1] in page
    assert "PARK_CLASS" in page
    assert "Class A" in page and "Class B" in page


def test_a_dataset_with_no_report_fields_is_one_colour(aoi, tmp_path):
    layer = _layer(_parks(tmp_path), summarize_fields=())

    page = _generate(aoi, [layer], tmp_path)[1].path.read_text(encoding="utf-8")

    assert SINGLE_LAYER_COLOUR in page
    assert LAYER_PALETTE[0] not in page


def test_a_field_with_too_many_values_is_one_colour(aoi, tmp_path):
    count = MAX_LEGEND_VALUES + 1
    gdf = gpd.GeoDataFrame(
        {"NAME": [f"Site {index}" for index in range(count)]},
        geometry=[Point(1_200_000 + index * 10, 460_500) for index in range(count)],
        crs="EPSG:3005",
    )
    layer = _layer(_save(tmp_path, "sites", gdf), title="Sites", summarize_fields=("NAME",))

    page = _generate(aoi, [layer], tmp_path)[1].path.read_text(encoding="utf-8")

    assert SINGLE_LAYER_COLOUR in page
    assert LAYER_PALETTE[0] not in page


def test_click_panel_lists_the_report_fields_only(aoi, tmp_path):
    """The click panel's copy of the layer carries the report fields and nothing
    else - not the id or the per-part measure."""
    page = _generate(aoi, [_layer(_parks(tmp_path))], tmp_path)[1].path.read_text(encoding="utf-8")

    assert 'var popupFields = ["PARK_CLASS"];' in page
    popup_data = page.split("var popupGeojson = ")[1].split(";\n")[0]
    assert "PARK_CLASS" in popup_data
    assert "OBJECTID" not in popup_data
    assert "overlap_area_m2" not in popup_data


def test_a_feature_saved_for_two_aoi_parts_is_shown_once(aoi, tmp_path):
    """A run saves one file per AOI part, and a feature that crosses two parts
    is in both, with a different overlap in each."""
    first = _parks(tmp_path, "part_1")
    second_gdf = gpd.read_file(first)
    second_gdf["overlap_area_m2"] = [5.0, 6.0]
    second = _save(tmp_path, "part_2", second_gdf)

    prepared = html_maps._prepare_layer(_layer(first, paths=(first, second)))

    assert len(prepared.display) == 2


def test_a_dataset_search_distance_is_offered_as_an_aoi_buffer(aoi, tmp_path):
    layer = _layer(_parks(tmp_path), buffer_m=250.0)

    page = _generate(aoi, [layer], tmp_path)[1].path.read_text(encoding="utf-8")

    assert "AOI buffer 250 m" in page
    assert "AOI buffer 1000 m" in page


def test_lines_and_points_in_one_dataset_are_both_drawn(aoi, tmp_path):
    gdf = gpd.GeoDataFrame(
        {"KIND": ["road", "gate"]},
        geometry=[LineString([(1_200_100, 460_100), (1_200_900, 460_900)]), Point(1_200_500, 460_500)],
        crs="EPSG:3005",
    )
    layer = _layer(_save(tmp_path, "mixed", gdf), title="Access", summarize_fields=("KIND",))

    prepared = html_maps._prepare_layer(layer)
    page = _generate(aoi, [layer], tmp_path)[1].path.read_text(encoding="utf-8")

    assert set(prepared.display.geometry.geom_type) == {"LineString", "Point"}
    assert "road" in page and "gate" in page


def test_a_file_dataset_is_shown_by_file_name_not_by_its_path(aoi, tmp_path):
    layer = _layer(_parks(tmp_path), datasource=r"\\server\share\secret\folder\parks.gdb\parks_fc")

    page = _generate(aoi, [layer], tmp_path)[1].path.read_text(encoding="utf-8")

    assert "parks_fc" in page
    assert "secret" not in page


# --- Values from the data never run as markup --------------------------------
def test_values_from_the_data_cannot_break_out_of_the_page(aoi, tmp_path):
    """A dataset's name and its attribute values are written into HTML and into
    a script block. Neither may be read as markup, as the end of the script, or
    as template syntax - folium reads the script it generates as a template, so
    an unescaped "{{ ... }}" would be run on the worker."""
    hostile = '</script><script>alert("x")</script>{% endraw %}{{ 7*7 }}'
    gdf = gpd.GeoDataFrame(
        {"NAME": [hostile]},
        geometry=[box(1_200_100, 460_100, 1_200_400, 460_400)],
        crs="EPSG:3005",
    )
    layer = _layer(_save(tmp_path, "hostile", gdf), title=f"Parks {hostile}", summarize_fields=("NAME",))

    page = _generate(aoi, [layer], tmp_path)[1].path.read_text(encoding="utf-8")

    assert '<script>alert("x")</script>' not in page
    # In the header it is plain escaped text.
    assert "&lt;/script&gt;" in page
    # In the data folium writes (hover values, layer names) the braces are HTML
    # entities, so there is no template syntax left for folium to run.
    assert "#123;\\u0026#123; 7*7 \\u0026#125;\\u0026#125;" in page
    # Still there for the click panel, escaped for a script block.
    assert "\\u003c/script\\u003e" in page
    assert "\\u0025 endraw \\u0025" in page


# --- The overview ------------------------------------------------------------
def test_overview_groups_its_layers_by_registry(aoi, tmp_path):
    layers = [
        _layer(_parks(tmp_path, "a"), title="Parks", group="provincial"),
        _layer(_parks(tmp_path, "b"), title="Local Parks", group="cariboo"),
    ]

    overview = _generate(aoi, layers, tmp_path)[0].path.read_text(encoding="utf-8")

    assert "AREA OF INTEREST" in overview
    assert "PROVINCIAL" in overview and "CARIBOO" in overview
    assert "Local Parks" in overview


def test_overview_carries_no_click_panel(aoi, tmp_path):
    """The click panel holds a second copy of a layer's data; with every dataset
    on one page that would be too much to load."""
    overview = _generate(aoi, [_layer(_parks(tmp_path))], tmp_path)[0].path.read_text(encoding="utf-8")

    assert "popupGeojson" not in overview


def test_an_aoi_in_latitude_and_longitude_is_accepted(aoi, tmp_path):
    outputs = _generate(aoi.to_crs("EPSG:4326"), [_layer(_parks(tmp_path))], tmp_path)

    assert len(outputs) == 2


def test_an_aoi_without_a_crs_is_refused(aoi, tmp_path):
    with pytest.raises(ValueError, match="CRS"):
        _generate(aoi.set_crs(None, allow_override=True), [_layer(_parks(tmp_path))], tmp_path)
