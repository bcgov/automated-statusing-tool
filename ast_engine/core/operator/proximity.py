"""
Proximity analysis Operator. Two analyses covered in this operator:

  within_distance: find every feature whose distance to the AOI is
                   less than or equal to a given radius.
  nearest        : find the top K closest features (regardless of distance,
                   with an optional distance cap).

Both return a list of ProximityResult records sorted by distance ascending.

Notes:
- The AOI CRS must be projected (metres). Distances are always reported in
  the CRS's native units, which we assume is metres for BC Albers (EPSG:3005).
- The adapter is called as-is. For Oracle, the caller passes the SDO
  push-down kwargs (predicate / distance / k / aoi). For local file adapters
  the dataset is read and filtered client-side 
- gpd.clip via ReadOptions.spatial_mask would alter feature geometries and
  break distance computation, so this module avoids that path entirely (for now!).
"""

from __future__ import annotations

from typing import Any, Iterable

import geopandas as gpd

from ..aoi import AreaOfInterest
from ..data_adapters.base import BaseSpatialAdapter, ReadOptions
from ..results import FeatureRecord, ProximityResult


_DISTANCE_COL = "_proximity_distance_m"


def within_distance(
    *,
    aoi: AreaOfInterest,
    adapter: BaseSpatialAdapter,
    distance_m: float,
    feature_id_field: str | None = None,
    keep_properties: Iterable[str] | None = None,
    read_options: ReadOptions | None = None,
    **adapter_kwargs,
) -> list[ProximityResult]:
    """Return every feature whose distance to the AOI is <= distance_m, ascending.

    The caller is responsible for telling the adapter how to filter the candidate
    set. For Oracle pass predicate='within_distance', distance=distance_m,
    aoi=<aoi_gdf> via adapter_kwargs. For file adapters the dataset is
    read and filtered.
    """
    if distance_m < 0:
        raise ValueError("distance_m must be non-negative")
    _require_projected(aoi)

    # Ask the adapter for the dataset features. 
    # The orchestrator can pre-tell the adapter how to filter (Oracle uses predicate="within_distance"
    gdf = adapter.read(
        read_options=read_options or _default_read_options(feature_id_field, keep_properties),
        target_crs=str(aoi.gdf.crs),
        **adapter_kwargs,
    )
    if gdf.empty:
        return []

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
    **adapter_kwargs,
) -> list[ProximityResult]:
    """Return up to k closest features, sorted by distance ascending.

    If max_distance_m is given, candidates beyond that distance are dropped
    (mirrors the legacy 25 km cap on archaeology sites).

    For Oracle the caller can pass predicate='nearest', k=k, aoi=<aoi_gdf>
    via adapter_kwargs so SDO_NN does the work push-down. For file adapters
    the dataset is read and sorted client-side.
    """
    if k < 1:
        raise ValueError("k must be at least 1")
    if max_distance_m is not None and max_distance_m < 0:
        raise ValueError("max_distance_m must be non-negative")
    _require_projected(aoi)

    # adapter read. For Oracle the orchestrator can use predicate="nearest" to push the work down to the database
    # for file adapters we get the full dataset and sort it.
    gdf = adapter.read(
        read_options=read_options or _default_read_options(feature_id_field, keep_properties),
        target_crs=str(aoi.gdf.crs),
        **adapter_kwargs,
    )
    if gdf.empty:
        return []

    aoi_geom = aoi.gdf.geometry.union_all()
    gdf = gdf.copy()
    gdf[_DISTANCE_COL] = gdf.geometry.distance(aoi_geom)
    if max_distance_m is not None:
        gdf = gdf[gdf[_DISTANCE_COL] <= max_distance_m]
    gdf = gdf.sort_values(_DISTANCE_COL).head(k)

    return _build_results(gdf, feature_id_field, keep_properties)


def _default_read_options(
    feature_id_field: str | None,
    keep_properties: Iterable[str] | None,
) -> ReadOptions:
    """Build a ReadOptions that keeps every column the operator needs downstream.

    Without this, passing keep_properties through `keep_columns` causes the base
    adapter to drop feature_id_field, and the result builder falls back to the
    row index. We always include feature_id_field in the keep set.
    """
    if not feature_id_field and not keep_properties:
        return ReadOptions()
    keep: set[str] = set()
    if feature_id_field:
        keep.add(feature_id_field)
    if keep_properties:
        keep.update(keep_properties)
    return ReadOptions(keep_columns=keep)


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
) -> list[ProximityResult]:
    """Turns the filtered/sorted GeoDataFrame into the typed ProximityResult 
        records the rest of the system expects.

        For each row of the GeoDataFrame it builds one ProximityResult containing:
            - the distance (pulled from the _proximity_distance_m column)
            - a FeatureRecord with the feature's ID and a dict of its other properties
        
        Returns the full list."""
    if gdf.empty:
        return []

    keep_list = list(keep_properties) if keep_properties else []
    results: list[ProximityResult] = []
    for idx, row in gdf.iterrows():
        results.append(
            ProximityResult(
                nearest_feature_distance=float(row[_DISTANCE_COL]),
                nearest_feature=FeatureRecord(
                    feature_id=_extract_feature_id(row, idx, feature_id_field),
                    properties=_extract_properties(row, keep_list),
                ),
            )
        )
    return results


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
