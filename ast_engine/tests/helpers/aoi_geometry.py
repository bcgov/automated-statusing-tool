# tests/helpers/aoi_geometry.py

from __future__ import annotations

import geopandas as gpd
from shapely.geometry import GeometryCollection, LineString, Point, Polygon, MultiPolygon, box

PROJECTED_CRS = "EPSG:3005"


def rect(
    xmin: float,
    ymin: float,
    xmax: float,
    ymax: float,
) -> Polygon:
    """Create a rectangular polygon."""
    return box(xmin, ymin, xmax, ymax)


def square(
    xmin: float,
    ymin: float,
    size: float,
) -> Polygon:
    """Create a square polygon from lower-left corner and size."""
    return box(xmin, ymin, xmin + size, ymin + size)


def multipolygon(
    *polygons: Polygon,
) -> MultiPolygon:
    return MultiPolygon(polygons)


def bowtie() -> Polygon:
    """Create a self-intersecting polygon."""
    return Polygon(
        [
            (0, 0),
            (100, 100),
            (0, 100),
            (100, 0),
            (0, 0),
        ]
    )


def polygon_line_collection() -> GeometryCollection:
    """Create a GeometryCollection with one polygon and one line."""
    return GeometryCollection(
        [
            rect(0, 0, 100, 100),
            LineString([(0, 0), (100, 100)]),
        ]
    )

def polygon_point_collection() -> GeometryCollection:
    """Create a GeometryCollection with one polygon and one point."""
    return GeometryCollection(
        [
            rect(0, 0, 100, 100),
            Point(50, 50),
        ]
    )


def line_point_collection() -> GeometryCollection:
    """Create a GeometryCollection with no polygonal geometry."""
    return GeometryCollection(
        [
            LineString([(0, 0), (100, 100)]),
            Point(50, 50),
        ]
    )


def aoi_gdf(
    geometries: list,
    *,
    crs: str = PROJECTED_CRS,
    **columns,
) -> gpd.GeoDataFrame:
    data = columns or {"id": list(range(1, len(geometries) + 1))}

    if crs is None:
        raise ValueError("CRS must be specified for AOI GeoDataFrame.")

    return gpd.GeoDataFrame(data, geometry=geometries, crs=crs)


def multipolygon_gdf() -> gpd.GeoDataFrame:
    return aoi_gdf(
        [
            multipolygon(
                rect(0, 0, 100, 100),
                rect(300, 300, 400, 400),
            )
        ],
        group_id=["A"],
    )


def disjoint_polygon_rows_gdf() -> gpd.GeoDataFrame:
    return aoi_gdf(
        [
            rect(0, 0, 100, 100),
            rect(300, 300, 400, 400),
        ],
        group_id=["A", "A"],
    )