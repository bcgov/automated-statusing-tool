"""
Adjacency analysis Operator. One analysis covered in this operator:

shared_border_summary: checks whether an Interest layer and a Query_Layer
share a boundary, and reports the total shared
border length.

The operator returns either a JSON string or a Python dictionary with:

LayerName : reported name of the query layer.
Shared_Border : true when shared boundary length is greater than zero.
Total_Length_m : total measured shared boundary length.
Count_Segments : number of merged shared boundary segments.

Notes:

- Inputs may be GeoDataFrames or pandas DataFrames with a geometry column.
- The Interest and Query_Layer geometries are dissolved before comparison so
- internal polygon boundaries are not counted as shared borders.
- Null, empty, and invalid geometries are removed or repaired before analysis.
- If distance_m is 0, boundaries must intersect exactly.
- If distance_m is greater than 0, Query_Layer boundary segments within that
- distance of the Interest boundary are counted as shared. This helps handle
  small slivers, minor misalignment, and coordinate precision issues.
- Measurements should be performed in a projected, metre-based CRS. Pass
  metric_crs='EPSG:3005' or another appropriate projected CRS when needed.
- Geographic CRS inputs are rejected because measuring boundary length in
  latitude/longitude would produce misleading results.
"""

import json
from typing import Union

import pandas as pd
import geopandas as gpd

from shapely.ops import unary_union, linemerge
from shapely.geometry import (
    LineString,
    MultiLineString,
    GeometryCollection,
)

try:
    from shapely.validation import make_valid
except ImportError:
    make_valid = None


def shared_border_summary(
    Interest: Union[pd.DataFrame, gpd.GeoDataFrame],
    Query_Layer: Union[pd.DataFrame, gpd.GeoDataFrame],
    distance_m: int = 0,
    layer_name: str = "Query_Layer",
    geometry_col: str = "geometry",
    metric_crs: str | int | None = None,
    return_json: bool = True,
) -> dict | str:
    """
    Checks whether Interest and Query_Layer share border/perimeter length.

    Parameters
    ----------
    Interest:
        GeoDataFrame or pandas DataFrame with a geometry column.

    Query_Layer:
        GeoDataFrame or pandas DataFrame with a geometry column.

    distance_m:
        Distance tolerance in metres.
        - 0 means boundaries must exactly intersect.
        - >0 means Query_Layer boundary segments within this distance
          of Interest boundary count as shared.

    layer_name:
        Name to report in the JSON output.

    geometry_col:
        Name of the geometry column.

    metric_crs:
        Optional CRS to project both layers into before measuring.
        Example: "EPSG:3005" for BC Albers.

    return_json:
        If True, returns a JSON string.
        If False, returns a Python dictionary.

    Returns
    -------
    dict or JSON string in the format:

    {
        "LayerName": "Query_Layer",
        "Shared_Border": true,
        "Total_Length_m": 123.45,
        "Count_Segments": 3
    }
    """

    if not isinstance(distance_m, int) or distance_m < 0:
        raise ValueError("distance_m must be an integer greater than or equal to 0.")

    interest_gdf = _ensure_geodataframe(Interest, geometry_col, "Interest")
    query_gdf = _ensure_geodataframe(Query_Layer, geometry_col, "Query_Layer")

    interest_gdf = _clean_geometries(interest_gdf)
    query_gdf = _clean_geometries(query_gdf)

    if interest_gdf.empty:
        raise ValueError("Interest has no valid geometries.")

    if query_gdf.empty:
        raise ValueError("Query_Layer has no valid geometries.")

    # Project both layers if a metric CRS is provided.
    if metric_crs is not None:
        interest_gdf = interest_gdf.to_crs(metric_crs)
        query_gdf = query_gdf.to_crs(metric_crs)

    # Otherwise, align Query_Layer to Interest CRS if possible.
    elif interest_gdf.crs is not None and query_gdf.crs is not None:
        if interest_gdf.crs != query_gdf.crs:
            query_gdf = query_gdf.to_crs(interest_gdf.crs)

    # Check that we are not measuring in latitude/longitude.
    if interest_gdf.crs is not None and interest_gdf.crs.is_geographic:
        raise ValueError(
            "Interest is in a geographic CRS. Reproject to a metre-based CRS first, "
            "or pass metric_crs='EPSG:3005' or another appropriate projected CRS."
        )

    if query_gdf.crs is not None and query_gdf.crs.is_geographic:
        raise ValueError(
            "Query_Layer is in a geographic CRS. Reproject to a metre-based CRS first, "
            "or pass metric_crs='EPSG:3005' or another appropriate projected CRS."
        )

    # Dissolve each layer so internal polygon boundaries are not counted.
    interest_union = unary_union(interest_gdf.geometry)
    query_union = unary_union(query_gdf.geometry)

    interest_boundary = interest_union.boundary
    query_boundary = query_union.boundary

    if distance_m == 0:
        # Exact shared boundary only.
        shared_geom = interest_boundary.intersection(query_boundary)

    else:
        # Tolerant shared boundary:
        # take parts of the Query_Layer boundary that fall within distance_m
        # of the Interest boundary.
        #
        # This handles small slivers, coordinate precision issues, and
        # slightly misaligned source datasets.
        interest_boundary_zone = interest_boundary.buffer(
            distance_m,
            cap_style="flat",
            join_style="mitre",
        )

        shared_geom = query_boundary.intersection(interest_boundary_zone)

    shared_lines = _extract_linework(shared_geom)

    if shared_lines:
        unioned_lines = unary_union(shared_lines)

        if isinstance(unioned_lines, LineString):
            merged_lines = [unioned_lines]

        else:
            merged = linemerge(unioned_lines)
            merged_lines = _extract_linework(merged)

    else:
        merged_lines = []

    total_length_m = sum(line.length for line in merged_lines)
    count_segments = len(merged_lines)

    result = {
        "LayerName": layer_name,
        "Shared_Border": total_length_m > 0,
        "Total_Length_m": round(total_length_m, 3),
        "Count_Segments": count_segments,
    }

    if return_json:
        return json.dumps(result, indent=4)

    return result


def _ensure_geodataframe(
    df: Union[pd.DataFrame, gpd.GeoDataFrame],
    geometry_col: str,
    name: str,
) -> gpd.GeoDataFrame:
    """
    Ensures input is a GeoDataFrame.
    """

    if isinstance(df, gpd.GeoDataFrame):
        if df.geometry.name != geometry_col and geometry_col in df.columns:
            return df.set_geometry(geometry_col)
        return df

    if isinstance(df, pd.DataFrame):
        if geometry_col not in df.columns:
            raise ValueError(f"{name} must contain a '{geometry_col}' column.")

        return gpd.GeoDataFrame(df, geometry=geometry_col)

    raise TypeError(f"{name} must be a pandas DataFrame or GeoPandas GeoDataFrame.")


def _clean_geometries(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Removes null/empty geometries and attempts to repair invalid geometries.
    """

    gdf = gdf.copy()

    gdf = gdf[
        gdf.geometry.notna()
        & ~gdf.geometry.is_empty
    ].copy()

    if make_valid is not None:
        gdf.geometry = gdf.geometry.apply(
            lambda geom: make_valid(geom) if not geom.is_valid else geom
        )
    else:
        gdf.geometry = gdf.geometry.apply(
            lambda geom: geom.buffer(0) if not geom.is_valid else geom
        )

    gdf = gdf[
        gdf.geometry.notna()
        & ~gdf.geometry.is_empty
    ].copy()

    return gdf


def _extract_linework(geom):
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