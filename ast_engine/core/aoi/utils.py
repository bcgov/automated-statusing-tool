"""Shared utilities and helpers for AOI calculations and checks."""

from __future__ import annotations

import geopandas as gpd
from shapely.geometry.base import BaseGeometry

  
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