"""Geometry conversion between Oracle/AOI and GeoDataFrame."""

import logging

import geopandas as gpd
import pandas as pd
from shapely import wkb, wkt

logger = logging.getLogger(__name__)


def aoi_to_wkb_srid(aoi: gpd.GeoDataFrame) -> tuple[bytes, int]:
    """Extract WKB bytes and EPSG SRID from the AOI geometry.

    An AOI can hold more than one row - the AOI policy only collapses it to a
    single row under `full_union`; `by_fields` and `preserve_features` both keep
    several. All rows are merged into one geometry here, because every SDO
    template binds a single AOI window. Taking one row instead would drop
    the rest from the query and silently under-read the table. Oracle accepts the
    resulting MultiPolygon in SDO_GEOMETRY, so no template changes are needed.

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

    geom = aoi.geometry.union_all()
    if geom.has_z:
        wkb_bytes = wkb.dumps(geom, output_dimension=2)
    else:
        wkb_bytes = wkb.dumps(geom)

    return wkb_bytes, srid


def aoi_to_wkt_srid(aoi: gpd.GeoDataFrame) -> tuple[str, int]:
    """Extract WKT text and EPSG SRID from the unioned AOI geometry.

    Z coordinates are dropped because overlays run in 2D.
    """
    if aoi.crs is None:
        raise ValueError("AOI has no CRS")

    srid = aoi.crs.to_epsg()
    if srid is None:
        raise ValueError(
            f"AOI CRS {aoi.crs!r} has no EPSG code; cannot bind to SDO_GEOMETRY"
        )

    geom = aoi.geometry.union_all()
    if geom.has_z:
        wkt_text = wkt.dumps(geom, output_dimension=2)
    else:
        wkt_text = geom.wkt

    return wkt_text, srid


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
