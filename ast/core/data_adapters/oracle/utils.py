"""Oracle table inspection and SQL post-processing helpers.

Pure functions that take `(connection, cursor, ...)`. Used by the
adapter to introspect table metadata (geometry column, SRID, columns)
and to patch query strings for known-quirky tables and SRID mismatches.
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
    """Return the SRID of the first row's geometry, or None if the table is empty."""
    sql = queries.SRID.format(tab=table, geom_col=geom_col)
    try:
        df = _read_query(cursor, sql, {})
    except Exception as exc:
        logger.warning("Cannot determine SRID for %s: %s", table, exc)
        return None
    if df.empty:
        logger.warning("Table %s is empty; cannot determine SRID", table)
        return None
    return int(df["SP_REF"].iloc[0]) if df["SP_REF"].iloc[0] is not None else None


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
