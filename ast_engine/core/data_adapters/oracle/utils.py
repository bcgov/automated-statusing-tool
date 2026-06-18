"""Helpers and post-processing functions for the Oracle data adapter.

Includes functions to patch query strings for known problematic tables (e.g. curved geometries) 
and for correcting SRID mismatches (e.g. 3005 vs 1000003005).
"""

import logging
from typing import Any

import pandas as pd

from . import queries

logger = logging.getLogger(__name__)


# Tables known to contain curved geometries that geopandas cannot parse.
# Server-side fix is applied via apply_geometry_fix() — see below.
PROBLEMATIC_TABLES = {
    "WHSE_CADASTRE.PMBC_PARCEL_FABRIC_POLY_FA_SVW",
    "WHSE_CADASTRE.PMBC_PARCEL_FABRIC_POLY_SVW",
}


# BCGW publishes some datasets against a local Albers mirror SRID that is not a
# real EPSG code (e.g. 1000003005 mirrors EPSG:3005, BC Albers). Map those
# mirror SRIDs to their true EPSG code so describe() records a valid CRS. Add
# more mirror -> EPSG entries here as they are found.
BCGW_SRID_TO_EPSG = {
    1000003005: 3005,
}


def _read_query(cursor: Any, sql: str, bind_vars: dict) -> pd.DataFrame:
    cursor.execute(sql, bind_vars)
    names = [d[0] for d in cursor.description]
    rows = cursor.fetchall()
    return pd.DataFrame(rows, columns=names)


def get_geometry_column(connection: Any, cursor: Any, table: str) -> str:
    """Return the SDO geometry column name for a fully-qualified table."""
    owner, tab_name = _split_table(table)
    df = _read_query(cursor, queries.GEOM_COL, {"owner": owner, "tab_name": tab_name})
    if df.empty:
        raise ValueError(
            f"No SDO geometry metadata found for {table} in ALL_SDO_GEOM_METADATA"
        )
    return df["GEOM_NAME"].iloc[0]


def get_srid(connection: Any, cursor: Any, table: str, geom_col: str) -> int | None:
    """Return the geometry SRID for a table, normalized to a real EPSG code.

    Reads the SRID from the SDO metadata dictionary first, which holds a row
    even for empty tables/views. Only when the dictionary carries no SRID does
    it fall back to sampling the first feature's geometry. Any BCGW Albers
    mirror SRID is mapped to its true EPSG code (see BCGW_SRID_TO_EPSG).
    Returns None when no SRID can be found by either route.
    """
    srid = _srid_from_metadata(cursor, table, geom_col)
    if srid is None:
        srid = _srid_from_row_sample(cursor, table, geom_col)
    if srid is None:
        return None
    return BCGW_SRID_TO_EPSG.get(srid, srid)


def _srid_from_metadata(cursor: Any, table: str, geom_col: str) -> int | None:
    """Return the SRID recorded in ALL_SDO_GEOM_METADATA, or None."""
    owner, tab_name = _split_table(table)
    try:
        df = _read_query(
            cursor,
            queries.SRID_METADATA,
            {"owner": owner, "tab_name": tab_name, "geom_col": geom_col},
        )
    except Exception as exc:
        logger.warning("SDO metadata SRID lookup failed for %s: %s", table, exc)
        return None
    if df.empty or df["SP_REF"].iloc[0] is None:
        return None
    return int(df["SP_REF"].iloc[0])


def _srid_from_row_sample(cursor: Any, table: str, geom_col: str) -> int | None:
    """Return the SRID of the first row's geometry, or None if empty."""
    sql = queries.SRID.format(tab=table, geom_col=geom_col)
    try:
        df = _read_query(cursor, sql, {})
    except Exception as exc:
        logger.warning("Cannot determine SRID for %s: %s", table, exc)
        return None
    if df.empty or df["SP_REF"].iloc[0] is None:
        logger.warning("Table %s is empty; cannot determine SRID", table)
        return None
    return int(df["SP_REF"].iloc[0])


def get_columns(connection: Any, cursor: Any, table: str) -> list[str]:
    """Return the list of column names available on the table."""
    owner, tab_name = _split_table(table)
    try:
        df = _read_query(
            cursor, queries.ALL_TAB_COLUMNS, {"owner": owner, "tab_name": tab_name}
        )
    except Exception as exc:
        logger.error("Failed to retrieve columns for %s: %s", table, exc)
        return []
    return df["COLUMN_NAME"].tolist() if not df.empty else []


# SDO_GTYPE type code -> normalized geometry type. SDO_GTYPE is a 4-digit
# number (DLTT); its last two digits are the geometry type: 1/5 point,
# 2/6 line, 3/7 polygon. Multipart variants (5/6/7) collapse to their
# single-part name. 4 (collection) and anything else is not handled here.
_GTYPE_TO_GEOMETRY_TYPE = {
    1: "point",
    5: "point",
    2: "line",
    6: "line",
    3: "polygon",
    7: "polygon",
}


def _gtype_to_geometry_type(gtype: int) -> str | None:
    """Map an Oracle SDO_GTYPE number to point, line or polygon.

    Returns None for geometry types AST does not handle (e.g. 4, a mixed
    collection).
    """
    return _GTYPE_TO_GEOMETRY_TYPE.get(int(gtype) % 100)


def get_geometry_type(
    connection: Any, cursor: Any, table: str, geom_col: str
) -> str | None:
    """Return the table's geometry type (point/line/polygon), or None.

    Reads SDO_GTYPE from the first row - no full scan. Returns None when the
    table is empty or holds a geometry type AST does not handle.
    """
    sql = queries.SDO_GTYPE.format(tab=table, geom_col=geom_col)
    try:
        df = _read_query(cursor, sql, {})
    except Exception as exc:
        logger.warning("Cannot determine geometry type for %s: %s", table, exc)
        return None
    if df.empty or df["GTYPE"].iloc[0] is None:
        logger.warning("Table %s is empty; cannot determine geometry type", table)
        return None
    return _gtype_to_geometry_type(df["GTYPE"].iloc[0])


def get_row_count(connection: Any, cursor: Any, table: str) -> int | None:
    """Return the row count: the fast estimate when available, else an exact count.

    First reads NUM_ROWS from ALL_TABLES - a fast lookup with no scan. That is
    null for views (the common BCGW case) and for tables whose stats have never
    been gathered; in that case it falls back to a COUNT(*). A COUNT(*) on a
    BCGW view is acceptable here because this runs once at registry build time,
    not per analysis. Returns None only if both the estimate and the count fail.
    """
    owner, tab_name = _split_table(table)
    try:
        df = _read_query(
            cursor, queries.NUM_ROWS, {"owner": owner, "tab_name": tab_name}
        )
        if not df.empty and df["NUM_ROWS"].iloc[0] is not None:
            return int(df["NUM_ROWS"].iloc[0])
    except Exception as exc:
        logger.warning("NUM_ROWS lookup failed for %s: %s", table, exc)

    # No estimate (view, or stats never gathered) - fall back to an exact count.
    try:
        df = _read_query(cursor, queries.ROW_COUNT.format(tab=table), {})
        return int(df["N"].iloc[0])
    except Exception as exc:
        logger.warning("COUNT(*) failed for %s: %s", table, exc)
        return None


def apply_geometry_fix(query: str, table: str, geom_col: str) -> str:
    """Densify + rectify the output geometry for tables in PROBLEMATIC_TABLES.

    Curved geometries (CURVEPOLYGON, COMPOUNDCURVE) and invalid rings are
    rare but present in PMBC parcel views. SDO_ARC_DENSIFY converts arcs
    to short line segments; RECTIFY_GEOMETRY repairs ring/orientation
    issues. Both run server-side before WKT serialization.

    No-op for any table not in PROBLEMATIC_TABLES.
    """
    if table not in PROBLEMATIC_TABLES:
        return query

    logger.info("Applying SDO_ARC_DENSIFY + RECTIFY_GEOMETRY for %s", table)
    original = f"SDO_UTIL.TO_WKTGEOMETRY({geom_col}) SHAPE"
    fixed = (
        "SDO_UTIL.TO_WKTGEOMETRY("
        "SDO_UTIL.RECTIFY_GEOMETRY("
        f"SDO_GEOM.SDO_ARC_DENSIFY({geom_col}, 0.005, 'arc_tolerance=0.5'), "
        "0.005)) SHAPE"
    )
    return query.replace(original, fixed)


def apply_coordinate_transform(query: str, geom_col: str, srid_t: int) -> str:
    """Wrap geometries in SDO_CS.TRANSFORM when AOI SRID != table SRID.

    Handles the common BCGW case of 3005 (BC Albers) vs 1000003005
    (its non-EPSG mirror). The adapter binds `:srid_t` separately.
    """
    logger.info("Applying coordinate transform (table SRID: %s)", srid_t)

    # Distance-based predicate (within_distance):
    query = query.replace(
        "SDO_GEOMETRY(:wkb_aoi, :srid),",
        "SDO_CS.TRANSFORM(SDO_GEOMETRY(:wkb_aoi, :srid), :srid_t),",
    )

    # Output WKT geometry — back-transform to the AOI's SRID for the caller:
    query = query.replace(
        f"SDO_UTIL.TO_WKTGEOMETRY({geom_col}) SHAPE",
        f"SDO_UTIL.TO_WKTGEOMETRY(SDO_CS.TRANSFORM({geom_col}, :srid)) SHAPE",
    )

    return query


def _split_table(table: str) -> tuple[str, str]:
    parts = table.split(".")
    if len(parts) != 2:
        raise ValueError(
            f"Table must be fully qualified as OWNER.NAME, got: {table!r}"
        )
    return parts[0].strip().upper(), parts[1].strip().upper()
