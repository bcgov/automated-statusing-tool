"""Geometry conversion between Oracle/AOI and GeoDataFrame.

Two pure helpers:
- aoi_to_wkb_srid(aoi):   GeoDataFrame -> (wkb_bytes, srid) for SQL bind vars
- df_to_gdf(df, srid):    DataFrame with WKT 'SHAPE' column -> GeoDataFrame
"""

import logging

import geopandas as gpd
import pandas as pd
from shapely import wkb

logger = logging.getLogger(__name__)


def aoi_to_wkb_srid(aoi: gpd.GeoDataFrame) -> tuple[bytes, int]:
    """Extract WKB bytes and EPSG SRID from the AOI geometry.

    The adapter passes these as `:wkb_aoi` and `:srid` bind variables.
    3D geometries are flattened to 2D (Oracle SDO_GEOMETRY constructed
    from WKB expects matching dimensions; AST overlays operate in 2D).
    """
    if aoi.crs is None:
        raise ValueError("AOI has no CRS")

    srid = aoi.crs.to_epsg()
    if srid is None:
        raise ValueError(
            f"AOI CRS {aoi.crs!r} has no EPSG code; cannot bind to SDO_GEOMETRY"
        )

    geom = aoi.geometry.iloc[0]
    if geom.has_z:
        wkb_bytes = wkb.dumps(geom, output_dimension=2)
    else:
        wkb_bytes = wkb.dumps(geom)

    return wkb_bytes, srid


def df_to_gdf(df: pd.DataFrame, srid: int) -> gpd.GeoDataFrame:
    """Convert a DataFrame with a WKT 'SHAPE' column to a GeoDataFrame.

    Queries are set to return a SHAPE column containing geometries as WKT strings via SDO_UTIL.TO_WKTGEOMETRY.
    This function rebuilds it as a shapely-backed geometry column and returns a GeoDataFrame.
    """
    shape_col = "SHAPE" if "SHAPE" in df.columns else "shape"
    if shape_col not in df.columns:
        raise ValueError("Expected a 'SHAPE' column in query result; none found")

    wkts = df[shape_col].astype(str)
    df_clean = df.drop(columns=[shape_col]).copy()
    df_clean["geometry"] = gpd.GeoSeries.from_wkt(wkts, crs=f"EPSG:{srid}")
    return gpd.GeoDataFrame(df_clean, geometry="geometry", crs=f"EPSG:{srid}")
