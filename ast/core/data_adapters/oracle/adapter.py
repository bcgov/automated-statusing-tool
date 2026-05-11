"""
OracleAdapter
Reads BCGW Oracle Spatial features related to an AOI and returns a geodataframe.
"""

import logging
from typing import Any, Literal

import geopandas as gpd
import oracledb

from data_adapters.base import BaseSpatialAdapter, ReadOptions
from data_adapters.exceptions import DataCrsError, DataReadError

from . import queries, utils
from .geometry import aoi_to_wkb_srid, df_to_gdf

logger = logging.getLogger(__name__)

Predicate = Literal["intersects", "within_distance", "touches", "nearest"]


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
        aoi: gpd.GeoDataFrame,
        predicate: Predicate = "intersects",
        distance: float | None = None,
        k: int | None = None,
        where: str | None = None,
        **_,
    ) -> gpd.GeoDataFrame:
        """Return features from a spatial query result.

        Predicates and their required kwargs:
          - intersects:        none
          - within_distance:   distance (metres)
          - touches:           none
          - nearest:           k (int)

        Consumes read_options.keep_columns and clears it before returning,
        so the base class post-filter does not strip adapter-emitted
        metadata columns (RESULT, DISTANCE_M). See PR description Q2.
        """
        try:
            return self._read(
                read_options=read_options,
                table=table,
                aoi=aoi,
                predicate=predicate,
                distance=distance,
                k=k,
                where=where,
            )
        except (DataReadError, DataCrsError):
            raise
        except oracledb.DatabaseError as exc:
            raise DataReadError(f"Oracle query failed for {table}: {exc}") from exc

    def _read(
        self,
        read_options: ReadOptions,
        table: str,
        aoi: gpd.GeoDataFrame,
        predicate: Predicate,
        distance: float | None,
        k: int | None,
        where: str | None,
    ) -> gpd.GeoDataFrame:
        # 1. Validate AOI shape - Review this later. will be handled upstream by AOI validator module!
        if aoi is None or aoi.empty:
            raise DataReadError("AOI is empty")
        if aoi.crs is None:
            raise DataReadError("AOI has no CRS")

        # 2. Validate predicate-specific kwargs
        if predicate == "within_distance":
            if distance is None or distance <= 0:
                raise DataReadError(
                    "predicate='within_distance' requires a positive `distance`"
                )
        elif predicate == "nearest":
            if k is None or not isinstance(k, int) or k <= 0:
                raise DataReadError(
                    "predicate='nearest' requires a positive integer `k`"
                )
        if predicate not in queries.PREDICATE_TEMPLATES:
            raise DataReadError(f"Unknown predicate: {predicate!r}")

        # 3. AOI -> WKB + SRID for bind variables
        wkb_aoi, srid = aoi_to_wkb_srid(aoi)

        # 4. Inspect table metadata - Review this later. Will be handled upstream by Data inventory module!
        geom_col = utils.get_geometry_column(self.connection, self.cursor, table)
        srid_t = utils.get_srid(self.connection, self.cursor, table, geom_col)
        if srid_t is None:
            raise DataReadError(
                f"Cannot determine SRID for {table} (table may be empty or have no SDO metadata)"
            )

        # 5. Resolve columns from read_options.keep_columns and consume it
        # (clearing prevents the base class post-filter from stripping the
        # adapter-emitted RESULT/DISTANCE_M metadata columns).
        keep = list(read_options.keep_columns) if read_options.keep_columns else None
        cols_csv = self._resolve_columns(table, keep)
        read_options.keep_columns = None

        # 6. Pick + format SQL template
        template = queries.PREDICATE_TEMPLATES[predicate]
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

        # 7. Server-side curve fix for known-problematic tables
        sql = utils.apply_geometry_fix(sql, table, geom_col)

        # 8. Coordinate transform if AOI SRID != table SRID
        bind_vars: dict[str, Any] = {"wkb_aoi": wkb_aoi, "srid": srid}
        if srid_t != srid:
            sql = utils.apply_coordinate_transform(sql, geom_col, srid_t)
            bind_vars["srid_t"] = srid_t
        if predicate == "nearest":
            bind_vars["k"] = k

        # 9. Execute
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

        # 10. Build GeoDataFrame from WKT (target_crs reprojection
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
