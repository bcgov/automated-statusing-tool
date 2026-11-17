"""
HTML maps: one interactive map per dataset, and an overview map of them all.

For each dataset a run found features in, this writes a standalone HTML page
showing those features over a basemap with the area of interest (AOI) drawn in
red. An overview page then shows every dataset together, grouped by the registry
it came from, so the whole status can be looked at on one map.

    00overview.html                  every dataset, switched on and off by layer
    <registry>__<dataset>.html       one dataset, with a legend and a click panel

This is the map output of the ArcGIS Pro Automated Status Tool (its
mapping/fc_to_html.py), carried over. The pages look and behave the same way:

  - the features are coloured by their first report field, with a legend, when
    that field has 20 or fewer different values; otherwise the layer is one colour;
  - hovering a feature shows its layer, report value, category and source;
  - clicking the map lists every feature under the click in a panel at the
    bottom left, and highlights them (clicking empty ground shows the lat/long);
  - the AOI is always on, and its buffers can be switched on.

What is different, because the engine gives the maps different inputs:

  - the features come from the GeoPackages the run saves (one per dataset per
    AOI part) rather than a file geodatabase of clipped feature classes;
  - a dataset whose registry gives it no category is grouped, on the overview,
    under the name of its registry;
  - colours come from a fixed palette, in order, so the same data always makes
    the same map (the ArcGIS Pro tool picked them at random);
  - a file dataset's source is shown by file name only, so a map does not carry
    internal network paths.

A page is plain HTML with its data inside it. It loads Leaflet, Turf and the BC
Sans font from their public CDNs and its basemap tiles from GeoBC and Esri, so
it needs internet access to draw, the same as the ArcGIS Pro tool's maps.
"""

from __future__ import annotations

import base64
import html
import json
import logging
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Optional

import folium
import geopandas as gpd
import pandas as pd
import shapely
from folium.plugins import GroupedLayerControl, MousePosition

logger = logging.getLogger(__name__)

# File name of the overview map. The "00" keeps it first in a folder listing.
OVERVIEW_MAP_NAME = "00overview"
OVERVIEW_MAP_TITLE = "Overview Map - All Overlaps"

# Text shown in every map's header and footer.
HEADER_ORGANIZATION = "Water, Land, and Resource Stewardship | Front Counter BC"
FOOTER_NOTICE = "Government of British Columbia | INTERNAL GOVERNMENT USE ONLY"

# The BC logo in the header, embedded in each page so a map is one file.
LOGO_PATH = Path(__file__).resolve().parent / "images" / "BCID_V_key_pms_pos_small_150px.jpg"

# Basemaps. The GeoBC tiles stop at zoom 16; the map lets the user go two
# levels further by stretching them.
GEOBC_BASEMAP_URL = "https://maps.gov.bc.ca/arcgis/rest/services/province/web_mercator_cache/MapServer/tile/{z}/{y}/{x}"
GEOBC_BASEMAP_ATTRIBUTION = "GeoBC, DataBC, TomTom, © OpenStreetMap Contributors"
IMAGERY_BASEMAP_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
IMAGERY_BASEMAP_ATTRIBUTION = "Tiles &copy; Esri"
MAX_BASEMAP_NATIVE_ZOOM = 16
MAX_USER_ZOOM = 18

# Scripts and fonts a page loads.
TURF_SCRIPT_URL = "https://unpkg.com/@turf/turf@6/turf.min.js"
BC_SANS_STYLESHEET_URL = "https://cdn.jsdelivr.net/gh/bcgov/bc-sans@main/css/BCSans.css"

# AOI buffers are measured in metres, so they are built in BC Albers.
WORK_CRS = "EPSG:3005"
# A web map is drawn in longitude/latitude.
WEB_CRS = "EPSG:4326"

# The overview map opens on the AOI with this much room around it, and the
# buffer is always offered as a layer.
OVERVIEW_BUFFER_M = 1000

# How much a layer is thinned for display: vertices closer together than the
# tolerance are dropped, and coordinates are snapped to the grid. Both in metres.
SIMPLIFY_TOLERANCE_M = 1.0
PRECISION_GRID_M = 0.001

# A layer is coloured by value only up to this many different values; beyond
# that the legend would be unreadable, so the layer is drawn in one colour.
MAX_LEGEND_VALUES = 20
SINGLE_LAYER_COLOUR = "#000000"
AOI_COLOUR = "red"
AOI_BUFFER_COLOUR = "orange"

# Colours for a layer's values, used in order. Twenty, to cover MAX_LEGEND_VALUES.
LAYER_PALETTE = (
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
    "#aec7e8", "#ffbb78", "#98df8a", "#ff9896", "#c5b0d5",
    "#c49c94", "#f7b6d2", "#c7c7c7", "#dbdb8d", "#9edae5",
)

# Fields shown in the click panel when a dataset names no report fields.
MAX_FALLBACK_POPUP_FIELDS = 5

# How close a click has to be to a line or a point to count as on it, in metres.
LINE_HIT_BUFFER_M = 5.0
POINT_HIT_DISTANCE_M = 5.0

# Sizes of the legend and of the space the footer takes, in pixels.
LEGEND_WIDTH_PX = 250
FOOTER_OFFSET_PX = 20

# Columns added to a layer for the map itself. Named so they cannot collide
# with a dataset's own columns.
_COLOUR_COL = "__colour__"
_TITLE_COL = "__layer__"
_GROUP_COL = "__category__"
_SOURCE_COL = "__source__"

# Columns the operators add to the saved features: a feature's own overlap or
# distance for one AOI part (see core/operator).
_MEASURE_COLUMNS = ("overlap_area_m2", "overlap_length_m", "distance_to_aoi_m")


@dataclass(frozen=True)
class MapLayer:
    """One dataset to map: what to call it and where its features are.

    title             the dataset's name, shown as the map title and layer name.
    group             the heading the overview map lists the dataset under: its
                      category, or the registry it came from when it has none.
    key               the caller's own id for the dataset, handed back on the
                      map that is written for it so the two can be matched up.
    datasource        the table or file the dataset was read from.
    paths             the GeoPackages holding the features the run matched, one
                      per AOI part (the run's spatial output).
    summarize_fields  the dataset's report fields (the registry
                      aggregate_columns). The first one present colours the
                      layer; all of them are listed in the click panel.
    buffer_m          the search distance for a within-distance dataset; drawn
                      as an AOI buffer layer. None for the other analyses.
    """

    title: str
    group: str
    datasource: str
    paths: tuple[Path, ...]
    summarize_fields: tuple[str, ...] = ()
    buffer_m: Optional[float] = None
    key: Optional[str] = None


@dataclass(frozen=True)
class MapOutput:
    """One map that was written.

    name   the file name without ".html". Letters, numbers, dashes and
           underscores only, so it is safe in a URL and a storage key.
    title  the title shown on the map.
    path   where the file is.
    key    the key of the MapLayer the map was made from; None for the overview.
    """

    name: str
    title: str
    path: Path
    key: Optional[str] = None


def generate_html_maps(
    *,
    aoi: gpd.GeoDataFrame,
    layers: Iterable[MapLayer],
    out_dir: str | Path,
    map_date: Optional[date] = None,
) -> list[MapOutput]:
    """Write one map per dataset that has features, then the overview map.

    aoi       the area of interest, in any projected or geographic CRS.
    layers    the datasets to map. A dataset with no features gets no map.
    out_dir   folder to write the .html files to; created if needed.
    map_date  the date printed in the footer; today when left out.

    Returns the maps written, the overview first. An empty list means no
    dataset had anything to map, and nothing was written.

    One dataset failing is logged and skipped so the rest are still mapped: a
    map that cannot be drawn must never cost the run its other maps.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    map_date = map_date or date.today()
    layers = list(layers)
    logo = _image_data_uri(LOGO_PATH)

    if aoi.crs is None:
        raise ValueError("AOI has no CRS.")
    aoi_projected = aoi if aoi.crs.is_projected else aoi.to_crs(WORK_CRS)
    aoi_web = _optimize_for_web(aoi_projected)
    buffers_web = _aoi_buffers(aoi_projected, layers)

    # The overview opens on the AOI and its surroundings.
    overview_bounds = buffers_web[OVERVIEW_BUFFER_M].total_bounds
    overview = _base_map(overview_bounds)
    overview_groups: dict[str, list[folium.FeatureGroup]] = {
        "AREA OF INTEREST": _add_aoi_layers(overview, aoi_web, buffers_web),
    }

    outputs: list[MapOutput] = []
    used_names: set[str] = set()
    for layer in layers:
        try:
            prepared = _prepare_layer(layer)
            if prepared is None:
                continue

            name = _unique_name(_slug(f"{layer.group}__{layer.title}"), used_names)
            path = out_dir / f"{name}.html"
            _write_dataset_map(path, layer, prepared, aoi_web, buffers_web, logo, map_date)
            outputs.append(MapOutput(name=name, title=layer.title, path=path, key=layer.key))

            group = _add_overview_layer(overview, layer, prepared)
            overview_groups.setdefault(layer.group.upper(), []).append(group)
        except Exception:
            logger.exception("Could not create the map for dataset %r; skipping it", layer.title)

    if not outputs:
        logger.info("No dataset had features to map; no maps written")
        return []

    overview_path = out_dir / f"{OVERVIEW_MAP_NAME}.html"
    _write_overview_map(overview_path, overview, overview_groups, logo, map_date)
    overview_output = MapOutput(name=OVERVIEW_MAP_NAME, title=OVERVIEW_MAP_TITLE, path=overview_path)
    return [overview_output, *outputs]


# ---------------------------------------------------------------------------
# Preparing a dataset for display
# ---------------------------------------------------------------------------

@dataclass
class _PreparedLayer:
    """A dataset's features made ready to draw.

    display      the features in EPSG:4326, thinned, with the map's own columns
                 (colour and the hover fields) and nothing else.
    popup        the same features with only the fields listed in the click panel.
    hover_fields / hover_aliases   the hover fields and the labels shown for them.
    popup_fields the fields listed in the click panel, in order.
    legend_header / legend_items   the legend's heading and its (colour, label) rows.
    """

    display: gpd.GeoDataFrame
    popup: gpd.GeoDataFrame
    hover_fields: list[str]
    hover_aliases: list[str]
    popup_fields: list[str]
    legend_header: str
    legend_items: list[tuple[str, str]]


def _prepare_layer(layer: MapLayer) -> Optional[_PreparedLayer]:
    """Read a dataset's features and work out how to draw them.

    Returns None when the dataset has nothing to map.
    """
    gdf = _read_features(layer.paths)
    if gdf is None or gdf.empty:
        return None

    geometry_column = gdf.geometry.name
    attribute_columns = [column for column in gdf.columns if column != geometry_column]

    # The report fields that are really on the data, in the registry's order.
    report_fields = [field for field in layer.summarize_fields if field in attribute_columns]
    # The field that colours the layer and labels a feature on hover: the first
    # report field, or failing that the first column the data has.
    label_field = report_fields[0] if report_fields else (attribute_columns[0] if attribute_columns else None)
    popup_fields = report_fields or _simple_fields(gdf, attribute_columns)

    # Everything shown is shown as text. Blank rather than "nan" for a missing value.
    for field in dict.fromkeys([field for field in [label_field, *popup_fields] if field]):
        gdf[field] = gdf[field].map(lambda value: "" if pd.isna(value) else str(value))

    legend_header, legend_items = _assign_colours(gdf, layer, label_field, has_report_fields=bool(report_fields))

    # The hover fields. Leaflet writes their values into the page as HTML, so
    # they are escaped here; a value from a dataset must never run as markup.
    gdf[_TITLE_COL] = _html_text(layer.title)
    gdf[_GROUP_COL] = _html_text(layer.group)
    gdf[_SOURCE_COL] = _html_text(_display_source(layer.datasource))
    hover_fields = [_TITLE_COL, _GROUP_COL, _SOURCE_COL]
    hover_aliases = ["LAYER", "CATEGORY", "SOURCE"]
    display_columns = [_COLOUR_COL, *hover_fields]
    if label_field:
        hover_label = f"__hover_{label_field}__"
        gdf[hover_label] = gdf[label_field].map(_html_text)
        hover_fields.insert(1, hover_label)
        hover_aliases.insert(1, _html_text(label_field))
        display_columns.append(hover_label)

    display = _optimize_for_web(gdf, keep_columns=display_columns)
    if display.empty:
        return None
    # The click panel escapes its values in the browser, so these stay as they are.
    popup = _optimize_for_web(gdf, keep_columns=popup_fields)

    return _PreparedLayer(
        display=display,
        popup=popup,
        hover_fields=hover_fields,
        hover_aliases=hover_aliases,
        popup_fields=popup_fields,
        legend_header=legend_header,
        legend_items=legend_items,
    )


def _read_features(paths: Iterable[Path]) -> Optional[gpd.GeoDataFrame]:
    """Read a dataset's features from its GeoPackages into one frame.

    A run saves one file per AOI part, and a feature that crosses two parts is
    in both; the copies are dropped so it is drawn and listed once. Features are
    flattened to 2D, which is all a web map draws.
    """
    frames = [gpd.read_file(path) for path in paths if Path(path).is_file()]
    frames = [frame for frame in frames if not frame.empty]
    if not frames:
        return None

    gdf = pd.concat(frames, ignore_index=True)
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty]
    gdf = gdf.set_geometry(shapely.force_2d(gdf.geometry.values))
    if gdf.crs is None:
        raise ValueError("The saved features have no CRS.")

    # Two rows are the same feature when everything about them matches. The
    # per-part measures differ between parts, so they are left out of the check.
    # The geometry is compared as bytes, in a plain table: geometry objects
    # themselves cannot be hashed for the comparison.
    geometry_column = gdf.geometry.name
    compare = pd.DataFrame(gdf.drop(columns=[column for column in _MEASURE_COLUMNS if column in gdf.columns]))
    compare[geometry_column] = gdf.geometry.to_wkb()
    return gdf.loc[~compare.duplicated()].reset_index(drop=True)


def _simple_fields(gdf: gpd.GeoDataFrame, columns: list[str]) -> list[str]:
    """Pick a few plain-valued columns to list for a dataset with no report fields."""
    simple = []
    for column in columns:
        sample = gdf[column].dropna().head(5)
        if all(isinstance(value, (str, int, float, bool)) for value in sample):
            simple.append(column)
        if len(simple) >= MAX_FALLBACK_POPUP_FIELDS:
            break
    return simple


def _assign_colours(
    gdf: gpd.GeoDataFrame,
    layer: MapLayer,
    label_field: Optional[str],
    *,
    has_report_fields: bool,
) -> tuple[str, list[tuple[str, str]]]:
    """Give every feature a colour and return the legend that explains them.

    A layer is coloured by its label field's values when the dataset names
    report fields and there are few enough values to read in a legend.
    Otherwise the whole layer is one colour, labelled with the dataset's name.
    Colours are handed out in palette order over the sorted values, so the same
    data is always drawn the same way.
    """
    values = sorted(gdf[label_field].unique()) if label_field else []
    if not has_report_fields or not values or len(values) > MAX_LEGEND_VALUES:
        gdf[_COLOUR_COL] = SINGLE_LAYER_COLOUR
        return "Legend", [(SINGLE_LAYER_COLOUR, layer.title)]

    colours = {value: LAYER_PALETTE[index % len(LAYER_PALETTE)] for index, value in enumerate(values)}
    gdf[_COLOUR_COL] = gdf[label_field].map(colours)
    return label_field, [(colour, value) for value, colour in colours.items()]


def _display_source(datasource: str) -> str:
    """A dataset's source as shown on a map.

    A BCGW table is shown as it is (SCHEMA.TABLE). A file is shown by name only:
    its folder is an internal network path, which a map has no reason to carry.
    """
    text = str(datasource).strip()
    if "/" in text or "\\" in text:
        return re.split(r"[\\/]+", text.rstrip("\\/"))[-1]
    return text


def _optimize_for_web(
    gdf: gpd.GeoDataFrame,
    keep_columns: Iterable[str] = (),
) -> gpd.GeoDataFrame:
    """Return a lighter copy of a layer for display, in EPSG:4326.

    Keeps only the named columns and the geometry, thins the geometry and
    reduces its coordinate precision. The work is done in a projected CRS so the
    tolerances are in metres. A page holds its data inline, so this is what
    keeps a map of a large dataset small enough to open.
    """
    geometry_column = gdf.geometry.name
    columns = [column for column in dict.fromkeys(keep_columns) if column in gdf.columns]
    out = gdf[[*columns, geometry_column]].copy()
    out = out[out.geometry.notna() & ~out.geometry.is_empty]
    if out.empty:
        return out.to_crs(WEB_CRS)

    work = out if out.crs.is_projected else out.to_crs(WORK_CRS)
    work = work.set_geometry(work.geometry.simplify(SIMPLIFY_TOLERANCE_M, preserve_topology=True))
    try:
        work = work.set_geometry(work.geometry.set_precision(PRECISION_GRID_M))
    except Exception:
        # Snapping can fail on awkward geometry; the layer is still drawable
        # at full precision, only a little larger.
        logger.debug("Could not reduce coordinate precision; keeping full precision", exc_info=True)

    work = work[work.geometry.notna() & ~work.geometry.is_empty]
    return work.to_crs(WEB_CRS)


def _aoi_buffers(aoi_projected: gpd.GeoDataFrame, layers: list[MapLayer]) -> dict[int, gpd.GeoDataFrame]:
    """Build the AOI buffer layers, keyed by distance in metres, smallest first.

    One for every search distance the datasets use, and always the overview
    buffer. Built in the projected CRS so the distances are in metres.
    """
    distances = {OVERVIEW_BUFFER_M}
    distances.update(int(layer.buffer_m) for layer in layers if layer.buffer_m and layer.buffer_m > 0)
    return {
        distance: _optimize_for_web(
            gpd.GeoDataFrame(geometry=aoi_projected.buffer(distance), crs=aoi_projected.crs)
        )
        for distance in sorted(distances)
    }


def _geometry_family(geometry_type: str) -> str:
    """Collapse a geometry type to the family it is drawn as: polygon, line or point."""
    if "Polygon" in geometry_type:
        return "polygon"
    if "Line" in geometry_type:
        return "line"
    return "point"


# ---------------------------------------------------------------------------
# Building a map
# ---------------------------------------------------------------------------

def _base_map(bounds: Iterable[float]) -> folium.Map:
    """Create a map with the two basemaps, the mouse position readout, the scale
    bar and a button that returns to the starting view.

    bounds is (xmin, ymin, xmax, ymax) in longitude/latitude; the map opens on it.
    """
    xmin, ymin, xmax, ymax = (float(value) for value in bounds)
    map_obj = folium.Map(tiles=None, control_scale=False, max_zoom=MAX_USER_ZOOM)
    map_obj.fit_bounds([[ymin, xmin], [ymax, xmax]], max_zoom=MAX_USER_ZOOM)

    folium.TileLayer(
        tiles=GEOBC_BASEMAP_URL,
        name="GeoBC Basemap",
        attr=GEOBC_BASEMAP_ATTRIBUTION,
        overlay=False,
        control=True,
        max_native_zoom=MAX_BASEMAP_NATIVE_ZOOM,
        max_zoom=MAX_USER_ZOOM,
    ).add_to(map_obj)
    # Only one basemap is drawn at a time. The map opens on the GeoBC basemap;
    # imagery is there to switch to.
    folium.TileLayer(
        tiles=IMAGERY_BASEMAP_URL,
        name="Imagery Basemap",
        attr=IMAGERY_BASEMAP_ATTRIBUTION,
        overlay=False,
        control=True,
        show=False,
    ).add_to(map_obj)

    MousePosition().add_to(map_obj)

    map_name = map_obj.get_name()
    _add_html(map_obj, f"""
        <style>
            .leaflet-bottom.leaflet-right {{
                bottom: {FOOTER_OFFSET_PX}px !important;
                right: 20px !important;
            }}
            .leaflet-control-scale {{
                margin-right: {LEGEND_WIDTH_PX + 40}px !important;
            }}
        </style>

        <div style="position: fixed; top: 88px; left: 70px; z-index: 900;">
            <button id="refresh-view" style="font-weight:bold; color:#DE1610">Refresh View</button>
        </div>

        <script>
        document.addEventListener("DOMContentLoaded", function() {{
            var map = {map_name};

            L.control.scale({{
                position: "bottomright",
                metric: true,
                imperial: false,
                maxWidth: 160
            }}).addTo(map);

            // Back to the view the map opened on.
            document.getElementById("refresh-view").onclick = function() {{
                map.fitBounds([[{ymin}, {xmin}], [{ymax}, {xmax}]], {{ maxZoom: {MAX_USER_ZOOM} }});
            }};
        }});
        </script>
    """)
    return map_obj


def _add_aoi_layers(
    map_obj: folium.Map,
    aoi_web: gpd.GeoDataFrame,
    buffers_web: dict[int, gpd.GeoDataFrame],
) -> list[folium.FeatureGroup]:
    """Add the AOI (shown) and its buffers (hidden until switched on) to a map.

    Returns their layer groups, for the layer control.
    """
    groups = []

    aoi_group = folium.FeatureGroup(name="AOI", show=True)
    folium.GeoJson(data=aoi_web, name="AOI", style_function=_outline_style(AOI_COLOUR)).add_to(aoi_group)
    aoi_group.add_to(map_obj)
    groups.append(aoi_group)

    for distance, buffer_web in buffers_web.items():
        name = f"AOI buffer {distance} m"
        buffer_group = folium.FeatureGroup(name=name, show=False)
        folium.GeoJson(data=buffer_web, name=name, style_function=_outline_style(AOI_BUFFER_COLOUR)).add_to(buffer_group)
        buffer_group.add_to(map_obj)
        groups.append(buffer_group)

    return groups


def _outline_style(colour: str):
    """Style for an outline with no fill: the AOI and its buffers."""
    return lambda feature: {"color": colour, "fillColor": "none", "weight": 3}


def _add_dataset_layer(
    map_obj: folium.Map,
    layer: MapLayer,
    prepared: _PreparedLayer,
    *,
    show: bool,
) -> folium.FeatureGroup:
    """Add a dataset's features to a map as one switchable layer group.

    Polygons, lines and points are drawn differently, so a dataset holding more
    than one kind is added as one GeoJSON layer per kind, all in the same group.
    """
    # Leaflet writes a layer's name into the layer control as HTML.
    group = folium.FeatureGroup(name=_html_text(layer.title), show=show)
    tooltip_arguments = dict(
        fields=prepared.hover_fields,
        aliases=prepared.hover_aliases,
        labels=True,
        sticky=True,
        style="""
            background-color: #F0EFEF;
            border: 2px solid #003366;
            border-radius: 3px;
            box-shadow: 3px;
            font-size: 12px;
            padding: 6px;
        """,
    )

    families = prepared.display.geometry.geom_type.map(_geometry_family)
    for family in sorted(families.unique()):
        arguments: dict[str, Any] = {
            "data": prepared.display[families == family],
            "name": _html_text(layer.title),
            # A tooltip object belongs to one layer, so each layer gets its own.
            "tooltip": folium.GeoJsonTooltip(**tooltip_arguments),
            "style_function": _STYLES[family],
            "highlight_function": _HIGHLIGHT_STYLES[family],
        }
        if family == "point":
            arguments["marker"] = folium.CircleMarker(
                radius=6, fill=True, fill_opacity=0.9, color="black", weight=1,
            )
        folium.GeoJson(**arguments).add_to(group)

    group.add_to(map_obj)
    return group


def _feature_colour(feature: dict) -> str:
    return feature["properties"].get(_COLOUR_COL, "#3388ff")


# How a feature is drawn, by geometry family...
_STYLES = {
    "polygon": lambda feature: {
        "fillColor": _feature_colour(feature),
        "color": _feature_colour(feature),
        "weight": 2,
        "fillOpacity": 0.45,
        "opacity": 1.0,
    },
    "line": lambda feature: {"color": _feature_colour(feature), "weight": 4, "opacity": 1.0},
    "point": lambda feature: {
        "fillColor": _feature_colour(feature),
        "color": _feature_colour(feature),
        "radius": 6,
    },
}

# ...and how it changes while the mouse is over it.
_HIGHLIGHT_STYLES = {
    "polygon": lambda feature: {"weight": 4, "fillOpacity": 0.8},
    "line": lambda feature: {"weight": 6, "opacity": 1.0},
    "point": lambda feature: {"radius": 8, "weight": 3, "fillOpacity": 1.0},
}


def _write_dataset_map(
    path: Path,
    layer: MapLayer,
    prepared: _PreparedLayer,
    aoi_web: gpd.GeoDataFrame,
    buffers_web: dict[int, gpd.GeoDataFrame],
    logo: str,
    map_date: date,
) -> None:
    """Write one dataset's own map: its features, the AOI, a legend and the click panel."""
    map_obj = _base_map(prepared.display.total_bounds)
    aoi_groups = _add_aoi_layers(map_obj, aoi_web, buffers_web)
    dataset_group = _add_dataset_layer(map_obj, layer, prepared, show=True)

    if prepared.popup_fields and not prepared.popup.empty:
        _add_click_panel(map_obj, prepared.popup, prepared.popup_fields, layer.title)

    geometry_types = prepared.display.geometry.geom_type.map(_geometry_family)
    # The legend draws one kind of symbol; use the kind most of the layer is.
    symbol = geometry_types.mode().iloc[0]
    _add_legend(map_obj, _legend_html(prepared.legend_header, prepared.legend_items, symbol), max_height_px=250)

    # The first control switches basemaps; the grouped ones switch the overlays.
    folium.LayerControl().add_to(map_obj)
    GroupedLayerControl(
        groups={"AREA OF INTEREST": aoi_groups},
        exclusive_groups=False,
        collapsed=True,
    ).add_to(map_obj)
    GroupedLayerControl(
        groups={_html_text(layer.title): [dataset_group]},
        exclusive_groups=False,
        collapsed=True,
    ).add_to(map_obj)

    _save(map_obj, path, title=layer.title, logo=logo, map_date=map_date)


def _add_overview_layer(overview: folium.Map, layer: MapLayer, prepared: _PreparedLayer) -> folium.FeatureGroup:
    """Add a dataset to the overview map, switched off until the user turns it on.

    The overview carries every dataset, so each is added as its drawing layer
    only - no click panel, which would put a second copy of the data in the page.
    """
    return _add_dataset_layer(overview, layer, prepared, show=False)


def _write_overview_map(
    path: Path,
    overview: folium.Map,
    groups: dict[str, list[folium.FeatureGroup]],
    logo: str,
    map_date: date,
) -> None:
    """Finish the overview map and write it: legend, layer controls, branding."""
    _add_legend(overview, _legend_html("Overview", [], "polygon"), max_height_px=300)

    folium.LayerControl().add_to(overview)
    GroupedLayerControl(
        groups={_html_text(name): members for name, members in groups.items()},
        exclusive_groups=False,
        collapsed=False,
    ).add_to(overview)
    _make_layer_control_scrollable(overview)

    _save(overview, path, title=OVERVIEW_MAP_TITLE, logo=logo, map_date=map_date)


# ---------------------------------------------------------------------------
# Legend, layer control and click panel
# ---------------------------------------------------------------------------

def _legend_html(header: str, items: list[tuple[str, str]], symbol: str) -> str:
    """Build the legend's contents: one row per colour, then the AOI and its buffers.

    symbol is the kind of swatch to draw for the dataset's rows: polygon, line
    or point. The header and labels come from the data, so they are escaped.
    """
    rows = [f'<div style="font-weight: bold; margin-bottom: 8px;">{html.escape(header)}</div>']
    for colour, label in items:
        rows.append(
            f'<div class="map-legend-row">{_swatch(symbol, colour)}<span>{html.escape(str(label))}</span></div>'
        )
    rows.append(
        '<div class="map-legend-row" style="margin-top:8px;">'
        f'{_swatch("outline", AOI_COLOUR)}<span>AOI</span></div>'
    )
    rows.append(
        f'<div class="map-legend-row">{_swatch("outline", AOI_BUFFER_COLOUR)}<span>AOI buffers</span></div>'
    )
    return "\n".join(rows)


def _swatch(symbol: str, colour: str) -> str:
    """A small SVG drawing of how a layer looks on the map, for the legend."""
    if symbol == "line":
        shape = f'<line x1="1" y1="7" x2="21" y2="7" stroke="{colour}" stroke-width="4" />'
    elif symbol == "point":
        shape = f'<circle cx="11" cy="7" r="5" fill="{colour}" stroke="black" stroke-width="1" />'
    elif symbol == "outline":
        shape = f'<rect x="3" y="2" width="16" height="10" fill="none" stroke="{colour}" stroke-width="2" />'
    else:
        shape = f'<rect x="3" y="2" width="16" height="10" fill="{colour}" stroke="{colour}" stroke-width="1" />'
    return f'<svg width="22" height="14" style="margin-right:8px; vertical-align:middle;">{shape}</svg>'


def _add_legend(map_obj: folium.Map, legend_html: str, *, max_height_px: int) -> None:
    """Add the legend to the bottom right of a map, as a Leaflet control.

    As a control it stacks with the map's other controls instead of covering
    them, and it scrolls when it has more rows than fit.
    """
    _add_html(map_obj, f"""
        <style>
            .leaflet-bottom.leaflet-right .leaflet-control {{
                margin-right: 0 !important;
                margin-bottom: 8px !important;
            }}
            .map-legend-control {{
                width: {LEGEND_WIDTH_PX}px;
                max-height: {max_height_px}px;
                overflow-y: auto;
                box-sizing: border-box;
                background-color: #fff;
                padding: 10px;
                border-radius: 5px;
                border: 1px solid grey;
                box-shadow: 0 1px 5px rgba(0,0,0,0.35);
                font-family: Arial, sans-serif;
                font-size: 13px;
                line-height: 1.3;
            }}
            .map-legend-row {{
                display: flex;
                align-items: center;
                gap: 8px;
                margin-bottom: 5px;
            }}
        </style>

        <script>
        document.addEventListener("DOMContentLoaded", function() {{
            var map = {map_obj.get_name()};
            var legend = L.control({{ position: "bottomright" }});

            legend.onAdd = function() {{
                var div = L.DomUtil.create("div", "map-legend-control");
                div.innerHTML = {_script_json(legend_html)};

                // Clicking or scrolling the legend should not move the map.
                L.DomEvent.disableClickPropagation(div);
                L.DomEvent.disableScrollPropagation(div);
                return div;
            }};

            legend.addTo(map);
        }});
        </script>
    """)


def _make_layer_control_scrollable(map_obj: folium.Map, *, width_px: int = 360, max_height_px: int = 460) -> None:
    """Give the overview's layer list a fixed size, scrolling when it is long.

    The overview lists every dataset, which runs to far more rows than fit on a
    screen. The grouped control is the last layer control added to the map,
    which is how it is found.
    """
    map_name = map_obj.get_name()
    _add_html(map_obj, f"""
        <style>
            #{map_name} .overview-layer-control.leaflet-control-layers-expanded {{
                width: {width_px}px !important;
                max-height: {max_height_px}px !important;
                overflow: hidden !important;
                box-sizing: border-box !important;
            }}
            #{map_name} .overview-layer-control .leaflet-control-layers-list {{
                max-height: {max_height_px - 35}px !important;
                overflow-y: auto !important;
                overflow-x: hidden !important;
                padding-right: 8px !important;
                box-sizing: border-box !important;
            }}
            #{map_name} .overview-layer-control label {{
                white-space: normal !important;
                line-height: 1.25 !important;
                margin-bottom: 4px !important;
            }}
            #{map_name} .overview-layer-control .leaflet-control-layers-group {{
                margin-top: 14px !important;
                padding-top: 8px !important;
            }}
            #{map_name} .overview-layer-control .leaflet-control-layers-group:first-child {{
                margin-top: 0 !important;
                padding-top: 0 !important;
            }}
            #{map_name} .overview-layer-control .leaflet-control-layers-group-name {{
                display: block !important;
                font-weight: bold !important;
                margin-bottom: 6px !important;
            }}
        </style>

        <script>
        document.addEventListener("DOMContentLoaded", function() {{
            var mapContainer = document.getElementById("{map_name}");
            if (!mapContainer) return;

            var layerControls = mapContainer.querySelectorAll(".leaflet-control-layers");
            if (layerControls.length === 0) return;

            var groupedControl = layerControls[layerControls.length - 1];
            groupedControl.classList.add("overview-layer-control");

            L.DomEvent.disableClickPropagation(groupedControl);
            L.DomEvent.disableScrollPropagation(groupedControl);
        }});
        </script>
    """)


def _add_click_panel(
    map_obj: folium.Map,
    popup_gdf: gpd.GeoDataFrame,
    popup_fields: list[str],
    title: str,
) -> None:
    """Add the click panel to a dataset's map.

    Clicking the map finds every feature under the click - not only the one on
    top - lists their fields in a panel at the bottom left, and highlights
    them. Clicking where there is nothing shows the latitude and longitude.

    The features are tested in the browser with Turf, so a second, attribute-
    bearing copy of the layer is written into the page. That is why this is on a
    dataset's own map only, not the overview.

    Field values are escaped in the browser (escapeHtml) before they are shown.
    """
    features = json.loads(popup_gdf.to_json(drop_id=True, na="drop"))
    _add_html(map_obj, f"""
        <script src="{TURF_SCRIPT_URL}"></script>

        <style>
        #fixed-info-panel {{
            position: fixed;
            bottom: 70px;
            left: 20px;
            z-index: 9999;
            width: 380px;
            max-height: 450px;
            overflow-y: auto;
            background: white;
            border: 2px solid #003366;
            border-radius: 6px;
            padding: 10px 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.35);
            font-family: Arial, sans-serif;
            font-size: 13px;
            box-sizing: border-box;
            display: none;
        }}
        #fixed-info-panel button {{
            float: right;
            cursor: pointer;
            border: none;
            background: #eeeeee;
            border-radius: 4px;
            padding: 2px 7px;
            font-size: 12px;
        }}
        #fixed-info-panel button:hover {{
            background: #dddddd;
        }}
        </style>

        <div id="fixed-info-panel"></div>

        <script>
        var popupGeojson = {_script_json(features)};
        var popupFields = {_script_json(popup_fields)};
        var popupTitle = {_script_json(title)};

        document.addEventListener("DOMContentLoaded", function() {{
            var map = {map_obj.get_name()};
            var panel = document.getElementById("fixed-info-panel");

            var highlightLayer = L.geoJSON(null, {{
                style: function(feature) {{
                    return {{
                        color: "#ff6600",
                        weight: 3,
                        fillColor: "#ffcc66",
                        fillOpacity: 0.45
                    }};
                }},
                pointToLayer: function(feature, latlng) {{
                    return L.circleMarker(latlng, {{
                        radius: 8,
                        color: "#ff6600",
                        weight: 3,
                        fillColor: "#ffcc66",
                        fillOpacity: 0.75
                    }});
                }}
            }}).addTo(map);

            // Clicks and scrolling inside the panel should not reach the map.
            L.DomEvent.disableClickPropagation(panel);
            L.DomEvent.disableScrollPropagation(panel);

            function clearPanel() {{
                panel.style.display = "none";
                panel.innerHTML = "";
                highlightLayer.clearLayers();
            }}

            function showPanel(panelHtml) {{
                panel.innerHTML = "<button id='fixed-info-close'>X</button>" + panelHtml;
                panel.style.display = "block";

                document.getElementById("fixed-info-close").onclick = function(event) {{
                    event.stopPropagation();
                    clearPanel();
                    map.closePopup();
                }};
            }}

            function escapeHtml(value) {{
                return String(value)
                    .replace(/&/g, "&amp;")
                    .replace(/</g, "&lt;")
                    .replace(/>/g, "&gt;")
                    .replace(/"/g, "&quot;")
                    .replace(/'/g, "&#039;");
            }}

            function displayValue(value) {{
                if (value === null || value === undefined) {{
                    return "";
                }}
                return String(value).replace(/\\s+/g, " ").trim();
            }}

            function buildPanelHtml(overlapping) {{
                var panelHtml = "";

                panelHtml += "<div style='font-weight:bold; font-size:14px; margin-bottom:6px;'>";
                panelHtml += escapeHtml(popupTitle) + " (" + overlapping.length + " overlap" + (overlapping.length === 1 ? "" : "s") + ")";
                panelHtml += "</div>";

                panelHtml += "<div style='max-height:350px; overflow-y:auto; max-width:100%; width:auto; box-sizing:border-box;'>";

                overlapping.forEach(function(feature, index) {{
                    var properties = feature.properties || {{}};

                    if (index > 0) {{
                        panelHtml += "<hr style='border-top: 2px solid #003366; margin: 8px 0;'>";
                    }}

                    // Alternate the text colour so neighbouring features are easy to tell apart.
                    var colour = (index % 2 === 0) ? "#000000" : "#003366";

                    panelHtml += "<table style='width:100%; color:" + colour + "; border-collapse:collapse;'>";

                    popupFields.forEach(function(key) {{
                        panelHtml += "<tr>";
                        panelHtml += "<td style='padding-right:6px; vertical-align:top;'><b>" + escapeHtml(key) + "</b></td>";
                        panelHtml += "<td>" + escapeHtml(displayValue(properties[key])) + "</td>";
                        panelHtml += "</tr>";
                    }});

                    panelHtml += "</table>";
                }});

                panelHtml += "</div>";
                return panelHtml;
            }}

            function showLatLngPopup(e) {{
                L.popup()
                    .setLatLng(e.latlng)
                    .setContent(
                        "Lat: " + e.latlng.lat.toFixed(6) + "<br>" +
                        "Lng: " + e.latlng.lng.toFixed(6)
                    )
                    .openOn(map);
            }}

            map.on("click", function(e) {{
                var pt = turf.point([e.latlng.lng, e.latlng.lat]);
                var overlapping = [];

                popupGeojson.features.forEach(function(feature) {{
                    if (!feature.geometry) return;

                    var turfGeom = turf.feature(feature.geometry);
                    var type = feature.geometry.type;

                    // A polygon is hit when the click is inside it; a line or a
                    // point when the click is within a few metres of it.
                    var isMatch =
                        ((type === "Polygon" || type === "MultiPolygon") &&
                            turf.booleanPointInPolygon(pt, turfGeom)) ||

                        ((type === "LineString" || type === "MultiLineString") &&
                            turf.booleanPointInPolygon(
                                pt,
                                turf.buffer(turfGeom, {LINE_HIT_BUFFER_M}, {{ units: "meters" }})
                            )) ||

                        (type === "Point" &&
                            turf.distance(pt, turfGeom, {{ units: "meters" }}) < {POINT_HIT_DISTANCE_M}) ||

                        (type === "MultiPoint" &&
                            feature.geometry.coordinates.some(function(coordinates) {{
                                return turf.distance(pt, turf.point(coordinates), {{ units: "meters" }}) < {POINT_HIT_DISTANCE_M};
                            }}));

                    if (isMatch) {{
                        overlapping.push(feature);
                    }}
                }});

                if (overlapping.length === 0) {{
                    clearPanel();
                    showLatLngPopup(e);
                    return;
                }}

                // Features were found, so close any lat/long popup still open.
                map.closePopup();
                showPanel(buildPanelHtml(overlapping));

                highlightLayer.clearLayers();
                overlapping.forEach(function(feature) {{
                    highlightLayer.addData(feature);
                }});
            }});
        }});
        </script>
    """)


# ---------------------------------------------------------------------------
# Writing a page
# ---------------------------------------------------------------------------

def _save(map_obj: folium.Map, path: Path, *, title: str, logo: str, map_date: date) -> None:
    """Render a map to HTML, add the header and footer, and write the file."""
    page = map_obj.get_root().render()
    path.write_text(_add_branding(page, title=title, logo=logo, map_date=map_date), encoding="utf-8")


def _add_branding(page: str, *, title: str, logo: str, map_date: date) -> str:
    """Put the standard header and footer on a rendered map page.

    The header carries the BC logo, the organization and the map's title; the
    footer the internal-use notice and the map date. The map itself is resized
    to sit between the two. The title comes from the registry, so it is escaped.
    """
    head = f"""
    <title>{html.escape(title)}</title>
    <link rel="stylesheet" href="{BC_SANS_STYLESHEET_URL}" />
    <style>
    html, body {{
        height: 100%;
        margin: 0;
        padding: 0;
        overflow: hidden;
    }}
    :root {{
        --header-h: 80px;
        --footer-h: 44px;
    }}
    .folium-map,
    div[id^="map_"] {{
        position: absolute !important;
        top: var(--header-h) !important;
        left: 0 !important;
        right: 0 !important;
        bottom: var(--footer-h) !important;
        width: 100% !important;
        height: auto !important;
    }}
    </style>
    """

    header = f"""
    <div id="bc-header" style="
        position: fixed; top: 0; left: 0; right: 0;
        height: var(--header-h);
        background:#003366;color:white;padding:10px 20px;
        display:flex;align-items:center;font-family:'BC Sans', sans-serif;
        box-sizing: border-box;
        z-index: 9999;">
      <img src="{logo}" alt="Government of British Columbia" style="height:50px;margin-right:15px;">
      <div style="display:flex; flex-direction:column;">
        <div style="font-size:18px; font-weight:bold; color:white;">{html.escape(HEADER_ORGANIZATION)}</div>
        <div style="font-size:22px; font-weight:bold; color:#e3a82b;">{html.escape(title)}</div>
      </div>
    </div>
    """

    footer = f"""
    <div id="bc-footer" style="
        position: fixed; left: 0; right: 0; bottom: 0;
        height: var(--footer-h);
        background: #003366; color: white;
        font-size: 14px; font-family: 'BC Sans', sans-serif;
        z-index: 9999;
        display: flex; align-items: center;
        padding: 0 16px; box-sizing: border-box;">
      <div style="flex: 1;"></div>
      <div style="flex: 2; text-align: center; white-space: nowrap;">© {map_date.year} {html.escape(FOOTER_NOTICE)}</div>
      <div style="flex: 1; text-align: right; white-space: nowrap;">Map Date: {map_date.strftime("%B %d, %Y")}</div>
    </div>
    """

    # Each tag appears once in a page folium renders. count=1 keeps a "<body>"
    # that turns up inside the map's own data from being touched.
    page = page.replace("<head>", f"<head>{head}", 1)
    page = page.replace("<body>", f"<body>{header}", 1)
    # The footer goes before the last </body>, which is the page's own.
    body_end = page.rfind("</body>")
    return page[:body_end] + footer + page[body_end:]


def _html_text(value: Any) -> str:
    """Escape a value from the data for a place folium writes it into the page.

    Two things have to be made harmless. HTML: Leaflet shows layer names and
    hover values as markup, so the HTML characters are escaped. Template syntax:
    folium reads the script it generates as a Jinja template a second time, so
    a value holding "{{ ... }}" or "{% ... %}" would be run as a template on the
    worker. Braces are written as HTML entities, which the browser shows as
    braces and Jinja does not see at all.

    Use this for every string handed to a folium object. Text written through
    _add_html does not need it (see there).
    """
    return html.escape(str(value)).replace("{", "&#123;").replace("}", "&#125;")


def _add_html(map_obj: folium.Map, markup: str) -> None:
    """Add a block of HTML, CSS or script to a map's page, exactly as written.

    folium treats an element's text as a Jinja template. The block is wrapped
    in a raw section so braces in the script and in the data are left alone
    rather than read as template syntax. Data put into a block goes through
    _script_json, which keeps it from ending the raw section early.
    """
    map_obj.get_root().html.add_child(folium.Element("{% raw %}" + markup + "{% endraw %}"))


def _script_json(value: Any) -> str:
    """Turn a value into JSON that is safe to write inside a <script> block.

    Plain JSON is not: a string holding "</script>" would end the script, and
    one holding "{% endraw %}" would end the raw section _add_html wraps a block
    in. The characters those need are written as JSON unicode escapes, which the
    browser reads back as the same text.
    """
    text = json.dumps(value)
    for character in ("<", ">", "&", "%"):
        text = text.replace(character, f"\\u{ord(character):04x}")
    return text


def _image_data_uri(path: Path) -> str:
    """Read an image file into a data URI, so the page needs no separate file."""
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def _slug(name: str) -> str:
    """Make a name usable as a file name and in a URL.

    Anything that is not a letter, number, dash or underscore becomes an underscore.
    """
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_")
    return cleaned or "dataset"


def _unique_name(name: str, used: set[str]) -> str:
    """Return name, with a number added when another map already has it.

    Two datasets can come down to the same file name once the characters a file
    name cannot hold are replaced; neither map may overwrite the other.
    """
    candidate = name
    suffix = 2
    while candidate in used or candidate == OVERVIEW_MAP_NAME:
        candidate = f"{name}_{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate
