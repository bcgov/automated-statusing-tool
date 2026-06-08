"""
OracleAdapter
Reads BCGW Oracle Spatial features related to an AOI and returns a geodataframe.
"""

import logging
from typing import Any

import geopandas as gpd
import oracledb
from ..base import BaseSpatialAdapter, ReadOptions
from ..exceptions import DataCrsError, DataReadError

from . import queries, utils
from .geometry import aoi_to_wkb_srid, df_to_gdf

logger = logging.getLogger(__name__)


class OracleAdapter(BaseSpatialAdapter):
    """Adapter for BCGW Oracle datasets.

    The Oracle connection is provided by OracleConnection in connection.py
    and injected into this adapter
    """

    def __init__(self, connection: Any, cursor: Any):
        self.connection = connection
        self.cursor = cursor

    def _read_impl(
        self,
        *,
        read_options: ReadOptions,
        table: str,
        **_,
    ) -> gpd.GeoDataFrame:
        """Return features from a spatial query result.

        The spatial filter (AOI + predicate + distance/k) is read from
        read_options.spatial_filter and the attribute filter from
        read_options.definition_query. Both are pushed down into the SDO
        query. _read clears definition_query afterwards so the base class
        post-filter does not re-apply it on top of the already-filtered
        result.
        """
        try:
            return self._read(read_options=read_options, table=table)
        except (DataReadError, DataCrsError):
            raise
        except oracledb.DatabaseError as exc:
            raise DataReadError(f"Oracle query failed for {table}: {exc}") from exc

    def _read(
        self,
        read_options: ReadOptions,
        table: str,
    ) -> gpd.GeoDataFrame:
        # 1. Read the spatial filter (AOI + predicate + distance/k) and the
        # attribute filter from ReadOptions. Both are pushed down into the
        # SDO query below. Clear definition_query so the base class post-
        # filter does not re-apply it on top of the SDO WHERE clause.
        # spatial_filter does not need clearing - the base post-filter does
        # not read it. SpatialFilter has already validated the AOI,
        # predicate and distance/k.
        spatial_filter = read_options.spatial_filter
        if spatial_filter is None:
            raise DataReadError(
                "Oracle adapter needs read_options.spatial_filter (the AOI)"
            )
        aoi = spatial_filter.aoi
        predicate = spatial_filter.predicate
        distance = spatial_filter.distance
        k = spatial_filter.k
        where = read_options.definition_query
        read_options.definition_query = None

        # 2. AOI -> WKB + SRID for bind variables
        wkb_aoi, srid = aoi_to_wkb_srid(aoi)

        # 3. Inspect table metadata - Review this later. Will be handled upstream by Data inventory module!
        geom_col = utils.get_geometry_column(self.connection, self.cursor, table)
        srid_t = utils.get_srid(self.connection, self.cursor, table, geom_col)
        if srid_t is None:
            raise DataReadError(
                f"Cannot determine SRID for {table} (table may be empty or have no SDO metadata)"
            )

        # 4. Resolve columns from read_options.keep_columns into the SQL
        # SELECT. Not cleared - the SDO templates project to exactly the
        # requested columns (plus SHAPE), so the base class post-filter's
        # keep_columns slice keeps the same set the SQL already returned.
        keep = list(read_options.keep_columns) if read_options.keep_columns else None
        cols_csv = self._resolve_columns(table, keep)

        # 5. Pick + format SQL template
        template = queries.PREDICATE_TEMPLATES.get(predicate)
        if template is None:
            raise DataReadError(
                f"Oracle adapter has no SQL template for predicate {predicate!r}"
            )
        def_query = f"AND ({where.strip()})" if where and where.strip() else ""

        format_args = {
            "cols": cols_csv,
            "tab": table,
            "geom_col": geom_col,
            "def_query": def_query,
        }
        if predicate == "within_distance":
            format_args["distance"] = distance
        sql = template.format(**format_args)

        # 6. Server-side curve fix for known-problematic tables
        sql = utils.apply_geometry_fix(sql, table, geom_col)

        # 7. Coordinate transform if AOI SRID != table SRID
        bind_vars: dict[str, Any] = {"wkb_aoi": wkb_aoi, "srid": srid}
        if srid_t != srid:
            sql = utils.apply_coordinate_transform(sql, geom_col, srid_t)
            bind_vars["srid_t"] = srid_t
        if predicate == "nearest":
            bind_vars["k"] = k

        # 8. Execute
        logger.debug("Executing Oracle overlay query against %s", table)
        self.cursor.setinputsizes(wkb_aoi=oracledb.DB_TYPE_BLOB)
        self.cursor.execute(sql, bind_vars)
        names = [d[0] for d in self.cursor.description]
        rows = self.cursor.fetchall()

        if not rows:
            logger.info("No features found in %s for the given AOI/predicate", table)
            return gpd.GeoDataFrame(
                {n: [] for n in names if n != "SHAPE"},
                geometry=gpd.GeoSeries([], crs=f"EPSG:{srid}"),
                crs=f"EPSG:{srid}",
            )

        import pandas as pd
        df = pd.DataFrame(rows, columns=names)

        # 9. Build GeoDataFrame from WKT (target_crs reprojection
        # is handled by the base class wrapper).
        return df_to_gdf(df, srid=srid)

    # Resolve columns discrepancies between requested columns (from xlxs) and actual table columns - Review this later: will be handled upstream by Data inventory module!
    def _resolve_columns(
        self, table: str, requested: list[str] | None
    ) -> str:
        """Return a comma-separated column list for the SELECT clause.

        - None  -> all available columns
        - given -> intersect with available; fall back to OBJECTID if
                   none of the requested columns exist (preserves the
                   previous tool's behaviour)
        """
        available = utils.get_columns(self.connection, self.cursor, table)
        if not available:
            raise DataReadError(f"Could not list columns for {table}")

        available_upper = {c.upper() for c in available}

        if requested is None:
            return ",".join(available)

        kept = [c for c in requested if c.upper() in available_upper]
        if not kept:
            if "OBJECTID" in available_upper:
                logger.warning(
                    "None of the requested columns exist in %s; falling back to OBJECTID",
                    table,
                )
                return "OBJECTID"
            raise DataReadError(
                f"None of the requested columns {requested!r} exist in {table}"
            )
        return ",".join(kept)
