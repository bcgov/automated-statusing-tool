from __future__ import annotations

from typing import Any

import geopandas as gpd
from pyproj import CRS
from shapely.geometry.base import BaseGeometry

from .exceptions import SpatialDataError, DataCRSError, SpatialGeometryError


POLYGONAL_TYPES = {"Polygon", "MultiPolygon"}


def check_gdf(
    gdf: gpd.GeoDataFrame,
    *,
    req_projected_crs: bool = True,
    strict: bool = False,
    context: str = "AOI GeoDataFrame",
) -> None:
    """
    Validate that a GeoDataFrame is usable for AOI processing.

    strict=False:
        Minimum checks needed before normalization. Used on raw Geometries or raw AOI input.

    strict=True:
        Downstream-ready checks expected after normalization.
    """

    if gdf is None:
        raise SpatialDataError(f"{context} is None.")

    if not isinstance(gdf, gpd.GeoDataFrame):
        raise SpatialDataError(
            f"{context} must be a GeoDataFrame. "
            f"Got: {type(gdf).__name__}."
        )

    if gdf.empty:
        raise SpatialDataError(f"{context} is empty.")

    if gdf.crs is None:
        raise DataCRSError(f"{context} has no CRS.")

    crs = parse_crs(gdf.crs, label=f"{context} CRS")

    if req_projected_crs and not crs.is_projected:
        raise DataCRSError(
            f"{context} must use a projected CRS. Got: {crs.to_string()}."
        )

    geometry_col = get_geometry_column_name(gdf, context=context)

    if geometry_col not in gdf.columns:
        raise SpatialGeometryError(
            f"{context} active geometry column {geometry_col!r} is missing."
        )

    # Minimum mode stops here.
    # Raw AOI input may still contain null, empty, invalid, or non-polygon geometry
    # because the normalizer is responsible for cleaning/extracting usable geometry.
    if not strict:
        return

    geometry = gdf.geometry

    null_count = int(geometry.isna().sum())
    if null_count:
        raise SpatialGeometryError(
            f"{context} contains {null_count} null geometry record(s)."
        )

    empty_count = int(geometry.is_empty.sum())
    if empty_count:
        raise SpatialGeometryError(
            f"{context} contains {empty_count} empty geometry record(s)."
        )

    non_polygonal = geometry[~geometry.geom_type.isin(POLYGONAL_TYPES)]
    if not non_polygonal.empty:
        types = sorted(str(t) for t in non_polygonal.geom_type.dropna().unique())
        raise SpatialGeometryError(
            f"{context} must contain only polygonal geometry. Found: {types}."
        )

    invalid_count = int((~geometry.is_valid).sum())
    if invalid_count:
        raise SpatialGeometryError(
            f"{context} contains {invalid_count} invalid geometry record(s)."
        )


def get_geometry_column_name(
    gdf: gpd.GeoDataFrame,
    *,
    context: str,
) -> str:
    try:
        geometry_col = gdf.geometry.name
    except Exception as exc:
        raise SpatialGeometryError(
            f"{context} has no active geometry column."
        ) from exc

    if not geometry_col:
        raise SpatialGeometryError(
            f"{context} has no active geometry column."
        )

    return str(geometry_col)
    

def parse_crs(
    value: str | int | CRS,
    *,
    label: str,
) -> CRS:
    try:
        return CRS.from_user_input(value)
    except Exception as ex:
        raise DataCRSError(
            f"Invalid {label}: {value!r}. Error: {ex}"
        ) from ex
    

def has_area_overlaps(
    gdf: gpd.GeoDataFrame,
    *,
    area_tolerance: float = 0.0,
) -> bool:
    """
    Return True if any pair of geometries intersects with positive area.

    This is intended for polygon overlap checks where shared edges or shared
    vertices should not count as overlap.

    Null and empty geometries are ignored.
    """
    if gdf is None or gdf.empty or len(gdf) < 2:
        return False

    geometry = gdf.geometry
    spatial_index = gdf.sindex

    for i, geom in enumerate(geometry):
        if geom is None or geom.is_empty:
            continue

        candidate_indexes = spatial_index.query(
            geom,
            predicate="intersects",
        )

        for j in candidate_indexes:
            j = int(j)

            if j <= i:
                continue

            other = geometry.iloc[j]

            if other is None or other.is_empty:
                continue

            intersection = geom.intersection(other)

            if not intersection.is_empty and intersection.area > area_tolerance:
                return True

    return False


def count_vertices(
    geom: BaseGeometry | None,
) -> int:
    if geom is None or geom.is_empty:
        return 0

    if geom.geom_type == "Polygon":
        return _count_polygon_vertices(geom)

    if geom.geom_type == "MultiPolygon":
        return sum(
            _count_polygon_vertices(part)
            for part in geom.geoms
        )

    if hasattr(geom, "geoms"):
        return sum(
            count_vertices(part)
            for part in geom.geoms
        )

    if hasattr(geom, "coords"):
        return len(geom.coords)

    return 0


def _count_polygon_vertices(
    geom: BaseGeometry,
) -> int:
    count = len(geom.exterior.coords)

    for interior in geom.interiors:
        count += len(interior.coords)

    return count

def has_z(geom: BaseGeometry | None) -> bool:
    if geom is None or geom.is_empty:
        return False

    if hasattr(geom, "geoms"):
        return any(has_z(part) for part in geom.geoms)

    return bool(getattr(geom, "has_z", False))


def has_m(geom: BaseGeometry | None) -> bool:
    if geom is None or geom.is_empty:
        return False

    if hasattr(geom, "geoms"):
        return any(has_m(part) for part in geom.geoms)

    return bool(getattr(geom, "has_m", False))