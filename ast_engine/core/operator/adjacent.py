"""
Adjacency analysis Operator. One analysis covered in this operator:

adjacency: checks whether a dataset shares a boundary with the AOI, and
reports the total shared border length.

Returns ONE AdjacencyResult per dataset. Each adjacent feature is one feature
record carrying the length of the boundary it shares with the AOI, in metres;
the result's measure_value is the total shared border length (the sum) and
is_adjacent is true when that total is above zero. Features are reported with
the longest shared border first.

Notes:

- The dataset is read through its adapter. The AOI is dissolved before
  comparison and each dataset feature is measured against it, so a boundary
  shared between two dataset features is not counted as a shared border.
- Null, empty, and invalid geometries are removed or repaired before analysis.
- If tolerance_m is 0, boundaries must intersect exactly (a true touch); the
  'touches' filter is pushed down to the adapter.
- If tolerance_m is greater than 0, dataset boundary segments within that
  distance of the AOI boundary are counted as shared. This helps handle small
  slivers, minor misalignment, and coordinate precision issues; the
  'within_distance' filter is pushed down so those near-misses are not dropped
  at the source.
- Measurements should be performed in a projected, metre-based CRS. The adapter
  reprojects the dataset to the AOI CRS; a non-projected AOI is rejected.
"""

from __future__ import annotations

from typing import Any, Iterable

import geopandas as gpd
import pandas as pd

from shapely.ops import unary_union, linemerge
from shapely.geometry import LineString, MultiLineString, GeometryCollection

from ..aoi import AreaOfInterest
from ..data_adapters.base import BaseSpatialAdapter, ReadOptions, SpatialFilter
from ..results import AdjacencyResult, FeatureRecord

try:
    from shapely.validation import make_valid
except ImportError:
    make_valid = None


def adjacency(
    *,
    aoi: AreaOfInterest,
    adapter: BaseSpatialAdapter,
    tolerance_m: float = 0,
    feature_id_field: str | None = None,
    keep_properties: Iterable[str] | None = None,
    where: Any = None,
    read_options: ReadOptions | None = None,
    **source_kwargs,
) -> AdjacencyResult:
    """Return one AdjacencyResult for the dataset, features sorted by shared length descending.

    tolerance_m chooses the match: 0 is a true touch (exact shared edge), above 0
    counts dataset boundary within that distance of the AOI boundary as shared.

    feature_id_field (the registry unique_id) names the column that identifies each
    feature; keep_properties names attribute columns to carry onto the records.
    where, when given (the dataset's registry definition query), is pushed down as
    an attribute filter. The spatial push-down is built into the default ReadOptions
    ('touches', or 'within_distance' when tolerance_m > 0); an orchestrator can pass
    its own read_options instead. Dataset identity (table for Oracle, path/layer for
    files) travels in source_kwargs.
    """
    if tolerance_m < 0:
        raise ValueError("tolerance_m must be non-negative")
    _require_projected(aoi)

    # Ask the adapter for the candidate features (touches / within_distance pushed down).
    gdf = adapter.read(
        read_options=read_options or _default_read_options(
            aoi, tolerance_m, feature_id_field, keep_properties, where
        ),
        target_crs=str(aoi.gdf.crs),
        **source_kwargs,
    )
    if gdf.empty:
        return AdjacencyResult(is_adjacent=False, features=[])

    gdf = _clean_geometries(gdf)
    if gdf.empty:
        return AdjacencyResult(is_adjacent=False, features=[])

    # Dissolve the AOI so a boundary shared between two of its parts is not
    # counted; each dataset feature is then measured against it on its own, which
    # keeps the per-feature identity the records need.
    aoi_boundary = aoi.gdf.geometry.union_all().boundary
    if tolerance_m > 0:
        # Tolerant match: the dataset boundary that falls within tolerance_m of
        # the AOI boundary. Absorbs slivers, precision noise and small misalignment.
        match_target = aoi_boundary.buffer(tolerance_m, cap_style="flat", join_style="mitre")
    else:
        # Exact match: only boundary the feature shares with the AOI precisely.
        match_target = aoi_boundary

    return _build_result(gdf, match_target, feature_id_field, keep_properties)


def _build_result(
    gdf: gpd.GeoDataFrame,
    match_target,
    feature_id_field: str | None,
    keep_properties: Iterable[str] | None,
) -> AdjacencyResult:
    """Turn the cleaned rows into one AdjacencyResult, longest shared border first.

    Each feature's shared boundary is merged into clean segments and its length
    summed into the feature's `measure`; features that share no boundary are
    dropped. The result's total shared border (measure_value) is the sum, derived
    by the results model. is_adjacent is True when at least one feature shares a
    boundary.
    """
    keep_list = list(keep_properties) if keep_properties else []
    features = []
    for idx, row in gdf.iterrows():
        shared_lines = _merge_shared_lines(row.geometry.boundary.intersection(match_target))
        length = sum(line.length for line in shared_lines)
        if length <= 0:
            continue
        features.append(
            FeatureRecord(
                feature_id=_extract_feature_id(row, idx, feature_id_field),
                properties=_extract_properties(row, keep_list),
                measure=float(length),
            )
        )

    features.sort(key=lambda feature: feature.measure, reverse=True)
    return AdjacencyResult(is_adjacent=bool(features), features=features)


def _default_read_options(
    aoi: AreaOfInterest,
    tolerance_m: float,
    feature_id_field: str | None,
    keep_properties: Iterable[str] | None,
    where: Any = None,
) -> ReadOptions:
    """Build a ReadOptions that pushes the AOI filter down, applies the dataset's
    attribute filter (where), and keeps the columns the operator needs downstream.

    'touches' for an exact match (tolerance_m == 0); 'within_distance' for a
    tolerant match, so the slivers a tolerance is meant to catch are not filtered
    out at the source. Without keep_columns, the base adapter could drop
    feature_id_field and the result builder would fall back to the row index, so
    feature_id_field is always included in the keep set.
    """
    keep: set[str] = set()
    if feature_id_field:
        keep.add(feature_id_field)
    if keep_properties:
        keep.update(keep_properties)
    if tolerance_m > 0:
        spatial_filter = SpatialFilter(
            aoi=aoi.gdf, predicate="within_distance", distance=tolerance_m
        )
    else:
        spatial_filter = SpatialFilter(aoi=aoi.gdf, predicate="touches")
    return ReadOptions(spatial_filter=spatial_filter, where=where, keep_columns=keep or None)


def _require_projected(aoi: AreaOfInterest) -> None:
    """Make sure the AOI is in a projected CRS for shared boundary length calculation."""
    crs = aoi.gdf.crs
    if crs is None or not crs.is_projected:
        raise ValueError(
            f"AOI {aoi.aoi_id} must be in a projected CRS for adjacency analysis "
            "(shared boundary length is computed in CRS units, expected metres)."
        )


def _merge_shared_lines(shared_geom) -> list:
    """Merge the shared linework into clean, continuous segments.

    Pulls the line pieces out of the shared geometry (ignoring stray points or
    polygons), then stitches touching pieces together so one continuous shared
    edge is reported as one segment rather than many small ones.
    """
    shared_lines = _extract_linework(shared_geom)
    if not shared_lines:
        return []

    unioned_lines = unary_union(shared_lines)
    if isinstance(unioned_lines, LineString):
        return [unioned_lines]

    merged = linemerge(unioned_lines)
    return _extract_linework(merged)


def _clean_geometries(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Removes null/empty geometries and attempts to repair invalid geometries.
    """
    gdf = gdf.copy()

    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()

    if make_valid is not None:
        gdf.geometry = gdf.geometry.apply(
            lambda geom: make_valid(geom) if not geom.is_valid else geom
        )
    else:
        gdf.geometry = gdf.geometry.apply(
            lambda geom: geom.buffer(0) if not geom.is_valid else geom
        )

    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()

    return gdf


def _extract_linework(geom) -> list:
    """
    Extracts LineString objects from a Shapely geometry.
    Ignores points, polygons, and empty geometries.
    """
    if geom is None or geom.is_empty:
        return []

    if isinstance(geom, LineString):
        return [geom] if geom.length > 0 else []

    if isinstance(geom, MultiLineString):
        return [part for part in geom.geoms if part.length > 0]

    if isinstance(geom, GeometryCollection):
        lines = []
        for part in geom.geoms:
            lines.extend(_extract_linework(part))
        return lines

    return []


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
        if value is None or pd.isna(value):
            continue
        if isinstance(value, (int, float, str)):
            props[col] = value
        else:
            props[col] = str(value)
    return props
