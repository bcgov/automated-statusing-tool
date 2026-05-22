"""
Overlay analysis Operator. There is one analysis covered in this operator:

  intersection: find every feature that intersects the AOI,
                and puts these features in a list, sorted by area of overlap descending.

It return a list of PolyOverlayResult records sorted by overlap descending.

Notes:
- This script is heavily influenced by Moez's work on the Proximity Operator. 
- In the future, we may need to alter if the development team wants to adopt Pydantic more thoroughly.
- 

- From Moez: ⌄
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

from core.aoi import AreaOfInterest
from core.data_adapters.base import BaseSpatialAdapter, ReadOptions
from core.results import FeatureRecord, PolyOverlayResult 

_AREA_COL = "_intersection_area_m2"


def _require_projected(aoi: AreaOfInterest) -> None:
    """Make sure the AOI is in a projected CRS for distance calculation.
    Helper function that is used later. 
    """
    crs = aoi.gdf.crs
    if crs is None or not crs.is_projected:
        raise ValueError(
            f"AOI {aoi.aoi_id} must be in a projected CRS for overlay analysis "
            "(distances are computed in CRS units, expected metres)."
        )

def intersection(
    *,
    aoi: AreaOfInterest,
    adapter: BaseSpatialAdapter,
    feature_id_field: str | None = None,
    keep_properties: Iterable[str] | None = None,
    read_options: ReadOptions | None = None,
    **adapter_kwargs,
) -> list[PolyOverlayResult]:
    """Return every feature that intersects the AOI, descending in area overlap.

    The caller is responsible for telling the adapter how to filter the candidate
    set. For Oracle pass predicate='relate', area=area_m2, aoi=<aoi_gdf> via adapter_kwargs. 
    For file adapters the dataset is
    read and filtered.
    """
    _require_projected(aoi)

    # Ask the adapter for the dataset features. 
    # The orchestrator can pre-tell the adapter how to filter (Oracle uses predicate="relate"
    gdf = adapter.read(
        read_options=read_options or _default_read_options(feature_id_field, keep_properties),
        target_crs=str(aoi.gdf.crs),
        **adapter_kwargs,
    )
    if gdf.empty:
        return []

    #This is where the main analysis happens 
    #Create gdf of all overlaying geometries from registry 
    aoi_geom = aoi.gdf.geometry.union_all()
    
    #Make a copy so nothing gets broken 
    gdf = gdf.copy()


    gdf[_AREA_COL] = gdf.geometry.intersection(aoi_geom).area

    gdf = gdf[gdf[_AREA_COL] > 0]
    gdf = gdf.sort_values(_AREA_COL, ascending=False)



    # Hand the sorted rows to _build_results to turn them into the proper PolyOverlayResult records
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

def _build_results(
    gdf: gpd.GeoDataFrame,
    feature_id_field: str | None,
    keep_properties: Iterable[str] | None,
) -> list[PolyOverlayResult]:
    """Turns the filtered/sorted GeoDataFrame into the typed PolyOverlayResult 
        records the rest of the system expects.

        For each row of the GeoDataFrame it builds one PolyOverlayResult containing:
            - the area (pulled from the _intersection_area_m2 column)
            - a FeatureRecord with the feature's ID and a dict of its other properties
        
        Returns the full list."""
    if gdf.empty:
        return []

    keep_list = list(keep_properties) if keep_properties else []
    results: list[PolyOverlayResult] = []
    for idx, row in gdf.iterrows():
        results.append(
            PolyOverlayResult(
                total_area=float(row[_AREA_COL]),
                features=FeatureRecord(
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
