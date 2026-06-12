"""
Proximity analysis Operator. Two analyses covered in this operator:

  within_distance: find every feature whose distance to the AOI is
                   less than or equal to a given radius.
  nearest        : find the top K closest features (regardless of distance,
                   with an optional distance cap).

Both return one ProximityResult holding the matched features, sorted nearest
first. Each feature's `measure` is its distance to the AOI in metres; the
result's headline measure_value is the nearest (smallest) distance.

Notes:
- The AOI CRS must be projected (metres). Distances are always reported in
  the CRS's native units, which we assume is metres for BC Albers (EPSG:3005).
- The AOI push-down is built into the default ReadOptions as a SpatialFilter
  ('within_distance' with the radius, or 'nearest' with k); each adapter applies
  it its own way (Oracle SDO, file bbox). An orchestrator can pass its own
  read_options instead. Dataset identity (table / path / layer) travels in
  source_kwargs.
- Distances are computed client-side with shapely, so the operator never
  alters feature geometries.
"""

from __future__ import annotations

from typing import Any, Iterable

import geopandas as gpd

from core.aoi import AreaOfInterest
from core.data_adapters.base import BaseSpatialAdapter, ReadOptions
from core.results import FeatureRecord, ProximityResult


_DISTANCE_COL = "_proximity_distance_m"


def within_distance(
    *,
    aoi: AreaOfInterest,
    adapter: BaseSpatialAdapter,
    distance_m: float,
    feature_id_field: str | None = None,
    keep_properties: Iterable[str] | None = None,
    read_options: ReadOptions | None = None,
    **source_kwargs,
) -> ProximityResult:
    """Return one ProximityResult holding every feature within distance_m, nearest first.

    The default ReadOptions pushes a SpatialFilter(predicate='within_distance',
    distance=distance_m) down to the adapter; the exact distance is then checked
    client-side (the push-down can be approximate, e.g. a file bbox). Pass your
    own read_options to override. Dataset identity travels in source_kwargs.
    """
    if distance_m < 0:
        raise ValueError("distance_m must be non-negative")
    _require_projected(aoi)

    # Ask the adapter for the candidate features (within_distance pushed down).
    gdf = adapter.read(
        read_options=read_options or _default_read_options(
            SpatialFilter(aoi=aoi.gdf, predicate="within_distance", distance=distance_m),
            feature_id_field,
            keep_properties,
        ),
        target_crs=str(aoi.gdf.crs),
        **source_kwargs,
    )
    if gdf.empty:
        return ProximityResult(features=[])

    aoi_geom = aoi.gdf.geometry.union_all()
    gdf = gdf.copy()
    gdf[_DISTANCE_COL] = gdf.geometry.distance(aoi_geom)
    gdf = gdf[gdf[_DISTANCE_COL] <= distance_m]
    gdf = gdf.sort_values(_DISTANCE_COL)

    # Hand the sorted rows to _build_results to turn them into the proper ProximityResult records
    return _build_results(gdf, feature_id_field, keep_properties)


def nearest(
    *,
    aoi: AreaOfInterest,
    adapter: BaseSpatialAdapter,
    k: int = 1,
    max_distance_m: float | None = None,
    feature_id_field: str | None = None,
    keep_properties: Iterable[str] | None = None,
    read_options: ReadOptions | None = None,
    **source_kwargs,
) -> ProximityResult:
    """Return one ProximityResult holding up to k closest features, nearest first.

    If max_distance_m is given, candidates beyond that distance are dropped
    (mirrors the legacy 25 km cap on archaeology sites).

    The default ReadOptions pushes a SpatialFilter(predicate='nearest', k=k) down
    to the adapter (Oracle SDO_NN); file adapters read the dataset and the top-k is
    taken client-side. Pass your own read_options to override. Dataset identity
    travels in source_kwargs.
    """
    if k < 1:
        raise ValueError("k must be at least 1")
    if max_distance_m is not None and max_distance_m < 0:
        raise ValueError("max_distance_m must be non-negative")
    _require_projected(aoi)

    # adapter read (nearest pushed down); file adapters read all and we take top-k below.
    gdf = adapter.read(
        read_options=read_options or _default_read_options(
            SpatialFilter(aoi=aoi.gdf, predicate="nearest", k=k),
            feature_id_field,
            keep_properties,
        ),
        target_crs=str(aoi.gdf.crs),
        **source_kwargs,
    )
    if gdf.empty:
        return ProximityResult(features=[])

    aoi_geom = aoi.gdf.geometry.union_all()
    gdf = gdf.copy()
    gdf[_DISTANCE_COL] = gdf.geometry.distance(aoi_geom)
    if max_distance_m is not None:
        gdf = gdf[gdf[_DISTANCE_COL] <= max_distance_m]
    gdf = gdf.sort_values(_DISTANCE_COL).head(k)

    return _build_results(gdf, feature_id_field, keep_properties)


def _default_read_options(
    spatial_filter: SpatialFilter,
    feature_id_field: str | None,
    keep_properties: Iterable[str] | None,
) -> ReadOptions:
    """Build a ReadOptions that pushes the AOI filter down and keeps the columns
    the operator needs downstream.

    Without keep_columns, the base adapter could drop feature_id_field and the
    result builder would fall back to the row index, so feature_id_field is always
    included in the keep set.
    """
    keep: set[str] = set()
    if feature_id_field:
        keep.add(feature_id_field)
    if keep_properties:
        keep.update(keep_properties)
    return ReadOptions(spatial_filter=spatial_filter, keep_columns=keep or None)



def _require_projected(aoi: AreaOfInterest) -> None:
    """Make sure the AOI is in a projected CRS for distance calulcation.
    """
    crs = aoi.gdf.crs
    if crs is None or not crs.is_projected:
        raise ValueError(
            f"AOI {aoi.aoi_id} must be in a projected CRS for proximity analysis "
            "(distances are computed in CRS units, expected metres)."
        )


def _build_results(
    gdf: gpd.GeoDataFrame,
    feature_id_field: str | None,
    keep_properties: Iterable[str] | None,
) -> ProximityResult:
    """Turn the filtered/sorted GeoDataFrame into a single ProximityResult.

        Each matched feature becomes one FeatureRecord whose `measure` is its
        distance to the AOI in metres (rows arrive sorted nearest-first). The
        result's headline measure_value (the nearest distance) is derived from
        these by the results model.
    """
    keep_list = list(keep_properties) if keep_properties else []
    features = [
        FeatureRecord(
            feature_id=_extract_feature_id(row, idx, feature_id_field),
            properties=_extract_properties(row, keep_list),
            measure=float(row[_DISTANCE_COL]),
        )
        for idx, row in gdf.iterrows()
    ]
    return ProximityResult(features=features)


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
