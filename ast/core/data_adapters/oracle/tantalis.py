"""Tantalis AOI lookup.

Resolves a Tantalis Crown Tenure parcel identified by the triple
(file_number, disposition_id, parcel_id) to a GeoDataFrame in the
table's native SRID.

This is the source for "Tantalis"-input AST runs (vs. user-provided AOIs). 
Geometry validation and cleanup (multipart split,...) is the responsibility 
of the AOI validator module upstream — this function returns the raw BCGW geometry as-is.
"""

import logging
from typing import Any

import geopandas as gpd
import oracledb
import pandas as pd

from data_adapters.exceptions import DataReadError

from . import utils
from .geometry import df_to_gdf

logger = logging.getLogger(__name__)


TANTALIS_TABLE = "WHSE_TANTALIS.TA_CROWN_TENURES_SVW"

TANTALIS_AOI_SQL = """
    SELECT SDO_UTIL.TO_WKTGEOMETRY(a.SHAPE) SHAPE
    FROM WHSE_TANTALIS.TA_CROWN_TENURES_SVW a
    WHERE a.CROWN_LANDS_FILE = :file_nbr
      AND a.DISPOSITION_TRANSACTION_SID = :disp_id
      AND a.INTRID_SID = :parcel_id
"""


def fetch_tantalis_aoi(
    connection: Any,
    cursor: Any,
    file_number: str,
    disposition_id: int | str,
    parcel_id: int | str,
) -> gpd.GeoDataFrame:
    """Resolve a Tantalis Crown Tenure parcel to an AOI GeoDataFrame.

    The connection/cursor pair is provided by OracleConnection (same
    injection pattern as OracleAdapter). Raises DataReadError if no
    parcel matches the input triple.
    """
    bind_vars = {
        "file_nbr": file_number,
        "disp_id": disposition_id,
        "parcel_id": parcel_id,
    }

    try:
        cursor.execute(TANTALIS_AOI_SQL, bind_vars)
        names = [d[0] for d in cursor.description]
        rows = cursor.fetchall()
    except oracledb.DatabaseError as exc:
        raise DataReadError(f"Tantalis AOI lookup failed: {exc}") from exc

    if not rows:
        raise DataReadError(
            f"No Tantalis parcel found for file_number={file_number!r}, "
            f"disposition_id={disposition_id!r}, parcel_id={parcel_id!r}"
        )

    srid = utils.get_srid(connection, cursor, TANTALIS_TABLE, "SHAPE")
    if srid is None:
        raise DataReadError(f"Cannot determine SRID for {TANTALIS_TABLE}")

    df = pd.DataFrame(rows, columns=names)
    return df_to_gdf(df, srid=srid)
