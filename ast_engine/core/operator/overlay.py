"""
Overlay analysis operator.

  intersection: find every feature in a dataset that overlaps the AOI and
                summarise the overlap.

Returns ONE overlay result per dataset (not one per feature). The result type
follows the dataset's geometry:
  - polygon datasets -> PolyOverlayResult, total_area   = summed overlap area (m2)
  - line datasets    -> LineOverlayResult, total_length = summed overlap length (m)
  - point datasets   -> PointOverlayResult, measure_value = feature count

Each kept feature is one FeatureRecord. For polygons/lines its `measure` is its
own overlap (area / length); points carry no per-feature measure (count only).
Features are sorted by overlap descending.

Notes:
- The AOI CRS must be projected (metres); area/length are in the CRS's units,
  assumed metres for BC Albers (EPSG:3005).
- The "intersects" filter is pushed down to the adapter via a SpatialFilter; the
  exact overlap is then computed client-side with shapely, so geometries are
  never altered.
"""

from __future__ import annotations

from typing import Any, Iterable, Literal

import geopandas as gpd

from ..aoi import AreaOfInterest
from ..data_adapters.base import BaseSpatialAdapter, ReadOptions, SpatialFilter
from ..results import (
    FeatureRecord,
    LineOverlayResult,
    PointOverlayResult,
    PolyOverlayResult,
)

_MEASURE_COL = "_overlay_measure"

GeomKind = Literal["point", "line", "polygon"]


def intersection(
    *,
    aoi: AreaOfInterest,
    adapter: BaseSpatialAdapter,
    geom_type: GeomKind | None = None,
    feature_id_field: str | None = None,
    keep_properties: Iterable[str] | None = None,
    where: Any = None,
    read_options: ReadOptions | None = None,
    **source_kwargs,
) -> PointOverlayResult | LineOverlayResult | PolyOverlayResult:
    """Return one overlay result for the dataset, features sorted by overlap descending.

    geom_type, when given (from the dataset registry), selects the result type and
    the overlap measure. When None it is inferred from the returned geometries.

    where, when given (the dataset's registry definition query), is pushed down as
    an attribute filter so only the matching features are read. The spatial
    push-down ("intersects") is built into the default ReadOptions; an orchestrator
    can pass its own read_options instead. Dataset identity (table for Oracle,
    path/layer for files) travels in source_kwargs.
    """
    _require_projected(aoi)

    # Ask the adapter for the candidate features (intersects pushed down).
    gdf = adapter.read(
        read_options=read_options or _default_read_options(aoi, feature_id_field, keep_properties, where),
        target_crs=str(aoi.gdf.crs),
        **source_kwargs,
    )

    kind = geom_type or _infer_geom_kind(gdf)
    if gdf.empty:
        return _empty_result(kind)

    aoi_geom = aoi.gdf.geometry.union_all()
    gdf = gdf.copy()
    # Per-feature overlap measure: area for polygons, length for lines, and for
    # points a 1/0 "is it inside" flag so the > 0 filter keeps intersecting points
    # instead of dropping them (points have no area or length).
    gdf[_MEASURE_COL] = _overlap_measure(gdf.geometry, aoi_geom, kind)
    gdf = gdf[gdf[_MEASURE_COL] > 0]
    gdf = gdf.sort_values(_MEASURE_COL, ascending=False)

    return _build_result(gdf, kind, feature_id_field, keep_properties)


def _overlap_measure(
    geoms: gpd.GeoSeries,
    aoi_geom: Any,
    kind: GeomKind,
) -> Any:
    """Overlap of each feature with the AOI, by geometry kind.

    polygon -> intersection area, line -> intersection length, point -> 1.0 if
    the point falls inside the AOI else 0.0.
    """
    if kind == "polygon":
        return geoms.intersection(aoi_geom).area
    if kind == "line":
        return geoms.intersection(aoi_geom).length
    return geoms.intersects(aoi_geom).astype(float)


def _build_result(
    gdf: gpd.GeoDataFrame,
    kind: GeomKind,
    feature_id_field: str | None,
    keep_properties: Iterable[str] | None,
) -> PointOverlayResult | LineOverlayResult | PolyOverlayResult:
    """Turn the filtered/sorted rows into one typed overlay result.

    Polygons/lines carry a per-feature `measure` (their own overlap) and a
    dataset total (total_area / total_length = the sum). Points carry no
    per-feature measure; their headline measure_value is the feature count.
    """
    keep_list = list(keep_properties) if keep_properties else []
    has_measure = kind != "point"
    features = [
        FeatureRecord(
            feature_id=_extract_feature_id(row, idx, feature_id_field),
            properties=_extract_properties(row, keep_list),
            measure=float(row[_MEASURE_COL]) if has_measure else None,
        )
        for idx, row in gdf.iterrows()
    ]

    if kind == "polygon":
        total = float(gdf[_MEASURE_COL].sum()) if not gdf.empty else 0.0
        return PolyOverlayResult(features=features, total_area=total)
    if kind == "line":
        total = float(gdf[_MEASURE_COL].sum()) if not gdf.empty else 0.0
        return LineOverlayResult(features=features, total_length=total)
    return PointOverlayResult(features=features)


def _empty_result(kind: GeomKind) -> PointOverlayResult | LineOverlayResult | PolyOverlayResult:
    """An overlay result with no features, of the right type."""
    if kind == "polygon":
        return PolyOverlayResult(features=[], total_area=0.0)
    if kind == "line":
        return LineOverlayResult(features=[], total_length=0.0)
    return PointOverlayResult(features=[])


def _infer_geom_kind(gdf: gpd.GeoDataFrame) -> GeomKind:
    """Map the dataset's geometry type to one of the three overlay kinds.

    Empty frames default to polygon (the common case) - pass geom_type explicitly
    when the dataset type is known (e.g. from the registry) to be sure.
    """
    types = set(gdf.geom_type.dropna().unique()) if not gdf.empty else set()
    if any("Polygon" in t for t in types):
        return "polygon"
    if any("Line" in t for t in types):
        return "line"
    if any("Point" in t for t in types):
        return "point"
    return "polygon"


def _default_read_options(
    aoi: AreaOfInterest,
    feature_id_field: str | None,
    keep_properties: Iterable[str] | None,
    where: Any = None,
) -> ReadOptions:
    """Build a ReadOptions that pushes down the AOI ("intersects"), applies the
    dataset's attribute filter (where), and keeps the columns the operator needs
    downstream.

    Without keep_columns, the base adapter could drop feature_id_field and the
    result builder would fall back to the row index, so feature_id_field is always
    included in the keep set.
    """
    keep: set[str] = set()
    if feature_id_field:
        keep.add(feature_id_field)
    if keep_properties:
        keep.update(keep_properties)
    return ReadOptions(
        spatial_filter=SpatialFilter(aoi=aoi.gdf, predicate="intersects"),
        where=where,
        keep_columns=keep or None,
    )


def _require_projected(aoi: AreaOfInterest) -> None:
    """Make sure the AOI is in a projected CRS for area/length calculation."""
    crs = aoi.gdf.crs
    if crs is None or not crs.is_projected:
        raise ValueError(
            f"AOI {aoi.aoi_id} must be in a projected CRS for overlay analysis "
            "(area/length are computed in CRS units, expected metres)."
        )


def _extract_feature_id(row: Any, idx: Any, feature_id_field: str | None) -> str:
    """Figures out the right ID for a feature.

        Tries in this order:
        1. If the caller told us which column holds the ID (e.g., "OBJECTID")
           and that column exists on this row with a non-null value, use it.
        2. Otherwise, fall back to the row's positional index ("0", "1", …) so we always have some ID

    """
    if feature_id_field and feature_id_field in row.index:
        value = row[feature_id_field]
        if value is not None:
            return str(value)
    return str(idx)


def _extract_properties(row: Any, keep: list[str]) -> dict[str, str | int | float]:
    """Picks attribute columns to surface on the output record.

       Walks the list of column names the caller asked to keep. For each:
        - Skip if the column isn't on this row.
        - Skip if the value is null.
        - If the value is already a string/int/float, keep it as-is.
        - Anything else (dates, geometries, etc.), convert to string.
           This matches the FeatureRecord.properties type signature.

     Returns a {column_name: value} dict.
    """
    props: dict[str, str | int | float] = {}
    for col in keep:
        if col not in row.index:
            continue
        value = row[col]
        if value is None:
            continue
        if isinstance(value, (int, float, str)):
            props[col] = value
        else:
            props[col] = str(value)
    return props
