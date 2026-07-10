# tests/helpers/aoi_geometry.py

from __future__ import annotations

"""
Low-level geometry and GeoDataFrame helpers for AOI tests.

These helpers create small, controlled Shapely geometries and GeoDataFrames
for unit tests. They should be imported by test modules, not run directly
as pytest tests.
"""

import geopandas as gpd
from shapely.geometry import (
    GeometryCollection,
    LineString,
    MultiPolygon,
    Point,
    Polygon,
    box,
)

PROJECTED_CRS = "EPSG:3005"
WGS84_CRS = "EPSG:4326"


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


def squares(
    *,
    count: int,
    size: float,
    overlap: bool = False,
    xmin: float = 0.0,
    ymin: float = 0.0,
) -> list[Polygon]:
    """
    Create a list of square polygons.

    If overlap=True, adjacent squares overlap.
    If overlap=False, adjacent squares are separated.
    """
    if count <= 0:
        raise ValueError("count must be greater than 0")

    if size <= 0:
        raise ValueError("size must be greater than 0")

    spacing = size * 0.5 if overlap else size * 1.5

    return [
        square(
            xmin=xmin + i * spacing,
            ymin=ymin,
            size=size,
        )
        for i in range(count)
    ]

def multipolygon(
    *polygons: Polygon,
) -> MultiPolygon:
    """Create a MultiPolygon from polygon parts."""
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
    crs: str | None = PROJECTED_CRS,
    **columns,
) -> gpd.GeoDataFrame:
    """Create a GeoDataFrame for AOI tests."""
    data = columns or {"id": list(range(1, len(geometries) + 1))}

    return gpd.GeoDataFrame(
        data,
        geometry=geometries,
        crs=crs,
    )


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


def missing_crs_gdf() -> gpd.GeoDataFrame:
    return aoi_gdf(
        [rect(0, 0, 100, 100)],
        crs=None,
        group_id=["A"],
    )


def bowtie_gdf() -> gpd.GeoDataFrame:
    return aoi_gdf(
        [bowtie()],
        group_id=["A"],
    )


def overlapping_polygons_gdf() -> gpd.GeoDataFrame:
    return aoi_gdf(
        [
            rect(0, 0, 100, 100),
            rect(80, 80, 180, 180),
        ],
        group_id=["A", "A"],
    )

def mixed_geometry_kml_overlap_aoi() -> Polygon:
    """
    Create a raw AOI geometry that overlaps the mixed-geometry KML test file.

    The KML coordinates are longitude/latitude, so this geometry should be used
    with CRS EPSG:4326 if it is wrapped in a GeoDataFrame.
    """
    return rect(
        -121.240,
        51.325,
        -121.165,
        51.365,
    )


def squares_gdf(
    *,
    count: int,
    size: float,
    overlap: bool = False,
    xmin: float = 0.0,
    ymin: float = 0.0,
    crs: str | None = PROJECTED_CRS,
    **columns,
) -> gpd.GeoDataFrame:
    """
    Create a GeoDataFrame of square polygons for AOI tests.

    Delegates GeoDataFrame construction to aoi_gdf().
    """
    if count != len(columns.get("id", [])) and count != len(columns.get("group_id", [])):
        raise ValueError(
            "count must match the length of 'id' or 'group_id' columns if provided"
        )
    geometries = squares(
        count=count,
        size=size,
        overlap=overlap,
        xmin=xmin,
        ymin=ymin,
    )

    return aoi_gdf(
        geometries,
        crs=crs,
        **columns,
    )


def mixed_geometry_kml_overlap_aoi_gdf() -> gpd.GeoDataFrame:
    """
    Create an AOI GeoDataFrame that overlaps polygon, line, and point features
    in test_shape_a_mixed_geometry.kml.
    """
    return aoi_gdf(
        [mixed_geometry_kml_overlap_aoi()],
        crs=PROJECTED_CRS,
        group_id=["mixed_geometry_kml"],
    )