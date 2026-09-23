# ast_engine/core/data_adapters/duckdb/adapter.py

import logging
from typing import Any, Optional
from urllib.parse import urlparse
import json
import duckdb
import geopandas as gpd
import shapely
from pydantic import BaseModel, SecretStr

from ast_engine.core.data_adapters.base import (
    BaseSpatialAdapter,
    DatasetInfo,
    ReadOptions,
)
from ast_engine.core.data_adapters.exceptions import DataReadError, DataCrsError, AdapterConfigurationError
from ast_engine.core.data_adapters.where_compiler import compile_where

logger = logging.getLogger(__name__)


class DuckDBConfig(BaseModel):
    s3_endpoint_url: Optional[str] = None
    s3_access_key: Optional[str] = None
    s3_secret_key: Optional[SecretStr] = None
    s3_region: str = "ca-central-1"
    s3_use_ssl: bool = True


class DuckDBAdapter(BaseSpatialAdapter):
    """Adapter for querying GeoParquet reference layers from S3 via DuckDB."""

    def __init__(self, config: DuckDBConfig):
        self.config = config
        self._conn: Optional[duckdb.DuckDBPyConnection] = None

    def _get_connection(self) -> duckdb.DuckDBPyConnection:
        """Initializes and reuses a persistent DuckDB session."""
        if self._conn is not None:
            return self._conn

        conn = duckdb.connect(database=":memory:")
        conn.execute("INSTALL spatial; LOAD spatial;")
        conn.execute("INSTALL httpfs; LOAD httpfs;")

        if self.config.s3_endpoint_url:
            parsed = urlparse(self.config.s3_endpoint_url)
            endpoint = parsed.netloc or parsed.path
            conn.execute("SET s3_endpoint=?", [endpoint])
            conn.execute("SET s3_use_ssl=?;", [self.config.s3_use_ssl])
            conn.execute("SET s3_url_style='path';")

        if self.config.s3_access_key and self.config.s3_secret_key:
            conn.execute("SET s3_access_key_id=?;", [self.config.s3_access_key])
            conn.execute(
                "SET s3_secret_access_key=?;",
                [self.config.s3_secret_key.get_secret_value()],
            )
            conn.execute("SET s3_region=?;", [self.config.s3_region])

        self._conn = conn
        return self._conn

    def _read_impl(
        self,
        *,
        read_options: ReadOptions,
        source: str,
        geom_col: str | None = None,
        source_crs: str | None = None,
        **_,
    ) -> gpd.GeoDataFrame:
        conn = self._get_connection()

        # Resolve Geometry Column and CRS
        resolved_geom_meta = self._extract_geoparquet_geom_meta(source=source)
        resolved_geom = resolved_geom_meta['geometry_column']
        resolved_crs = resolved_geom_meta['crs']
        if not resolved_crs and source_crs is None:
            raise DataCrsError(f"Could not auto-detect CRS for {source}. Please specify `source_crs`.")
        if not resolved_geom and geom_col is None:
            raise DataCrsError(f"Could not auto-detect Geometry Column for {source}. Please specify `geom_col`.")
        if source_crs and source_crs != resolved_crs:
            raise AdapterConfigurationError(f"source_crs ({source_crs}) is different than detected source crs ({resolved_crs})")
        if geom_col and geom_col != resolved_geom:
            raise AdapterConfigurationError(f"geom_col ({geom_col}) is different than detected source crs ({resolved_geom})")
        if resolved_geom:
            geom_col = resolved_geom
        if resolved_crs:
            source_crs = resolved_crs

        # Fetch Columns
        try:
            schema_df = conn.execute("DESCRIBE SELECT * FROM read_parquet(?)", [source]).fetchdf()
        except duckdb.Error as exc:
            raise DataReadError(f"Failed to read metadata from {source}: {exc}") from exc
            
        available_cols = schema_df["column_name"].tolist()
        
        # Attribute filter compilation & clear (consume-and-clear to prevent base class post-filtering)
        where_model = read_options.where
        legacy_query = read_options.definition_query
        read_options.where = None
        read_options.definition_query = None

        where_sql = None
        if where_model is not None:
            # DuckDB syntax aligns closer to PostgreSQL than SQLite
            where_sql = compile_where(where_model, dialect="postgresql")
        elif legacy_query and legacy_query.strip():
            where_sql = legacy_query.strip()

        # Column selection pushdown
        if read_options.keep_columns:
            kept = [c for c in read_options.keep_columns if c in available_cols and c != geom_col]
            if kept:
                quoted_cols = [f'"{col}"' for col in kept]
                cols_str = ", ".join(quoted_cols) + ", "
            else:
                logger.warning(f"None of the requested columns exist in {source}; selecting all attributes.")
                cols_str = f"* EXCLUDE ({geom_col}), "
        else:
            cols_str = f"* EXCLUDE ({geom_col}), "

        query = f"""
            SELECT {cols_str} ST_AsWKB({geom_col}) AS wkb_geometry 
            FROM read_parquet(?)
            WHERE 1=1
        """
        params: list[Any] = [source]

        # 3. Spatial filter pushdown
        sf = read_options.spatial_filter
        if sf and sf.aoi is not None and not sf.aoi.empty:
            aoi_wkt = sf.aoi.geometry.unary_union.wkt
            pred = sf.predicate.lower()

            if pred == "intersects":
                query += f" AND ST_Intersects({geom_col}, ST_GeomFromText(?))"
                params.append(aoi_wkt)
            elif pred == "within_distance" and sf.distance is not None:
                query += f" AND ST_DWithin({geom_col}, ST_GeomFromText(?), ?)"
                params.extend([aoi_wkt, sf.distance])
            elif pred == "touches":
                query += f" AND ST_Touches({geom_col}, ST_GeomFromText(?))"
                params.append(aoi_wkt)

        # 4. Apply compiled where clause
        if where_sql:
            query += f" AND ({where_sql})"

        logger.info(f"Executing DuckDB S3 query on {source}")
        try:
            df = conn.execute(query, params).fetchdf()
        except duckdb.Error as exc:
            raise DataReadError(f"Failed to read Parquet from {source}: {exc}") from exc

        if df.empty:
            logger.info(f"No records returned for query on {source}")
            cols = [c for c in df.columns if c != "wkb_geometry"]
            return gpd.GeoDataFrame(columns=cols, geometry=[], crs=source_crs)

        # 5. WKB geometry parsing
        geometries = shapely.from_wkb(df["wkb_geometry"].apply(bytes))
        df.drop(columns=["wkb_geometry"], inplace=True)

        return gpd.GeoDataFrame(df, geometry=geometries, crs=source_crs)

    def describe(
        self, 
        *, 
        source: str, 
        geom_col: str = "geometry", 
        source_crs: str = "EPSG:4326", 
        **kwargs: Any
    ) -> DatasetInfo:
        conn = self._get_connection()
        try:
            schema_df = conn.execute("DESCRIBE SELECT * FROM read_parquet(?)", [source]).fetchdf()
            cols = schema_df["column_name"].tolist()
            attr_cols = [c for c in cols if c != geom_col]

            count_df = conn.execute("SELECT COUNT(*) AS cnt FROM read_parquet(?)", [source]).fetchdf()
            row_count = int(count_df["cnt"].iloc[0])
        except duckdb.Error as exc:
            raise DataReadError(f"Failed to describe Parquet file at {source}: {exc}") from exc

        return DatasetInfo(
            geom_column=geom_col,
            crs=source_crs,
            geometry_type="polygon",  # Defaulting to polygon, consider pulling from metadata if available
            columns=attr_cols,
            row_count=row_count,
        )

    def _extract_geoparquet_geom_meta(self, source: str) -> Optional[str]:
        """Attempts to read CRS from GeoParquet metadata."""
        conn = self._get_connection()
        try:
            res = conn.execute(
                "SELECT value FROM parquet_kv_metadata(?) WHERE key = 'geo'", 
                [source]
            ).fetchone()
            
            if res and res[0]:
                geo_meta = json.loads(res[0])
                primary_col = geo_meta.get("primary_column", "geometry")
                crs_meta = geo_meta.get("columns", {}).get(primary_col, {}).get("crs")

                if isinstance(crs_meta, dict):
                    id_info = crs_meta.get("id", {})
                    if "authority" in id_info and "code" in id_info:
                        return {"geometry_column":primary_col, "crs": f"{id_info['authority']}:{id_info['code']}"}
                elif isinstance(crs_meta, str):
                    return {"geometry_column":primary_col,"crs":crs_meta}
        except duckdb.Error:
            pass
        return None