import logging
from typing import Any, Optional
from urllib.parse import urlparse

import duckdb
import geopandas as gpd
import shapely
from pydantic import BaseModel, SecretStr

from ast_engine.core.data_adapters.base import (
    BaseSpatialAdapter,
    DatasetInfo,
    ReadOptions,
)
from ast_engine.core.data_adapters.exceptions import DataReadError
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
        source_path: str,
        geom_col: str = "geometry",
        source_crs: str = "EPSG:4326",
        **kwargs: Any,
    ) -> gpd.GeoDataFrame:
        conn = self._get_connection()

        # Inspect parquet schema to auto-resolve actual geometry column name
        schema_df = conn.execute("DESCRIBE SELECT * FROM read_parquet(?)", [source_path]).fetchdf()
        available_cols = schema_df["column_name"].tolist()

        # Find matching column (case-insensitive match or common fallbacks)
        matched_geom = next(
            (c for c in available_cols if c.lower() == geom_col.lower()), None
        )
        if not matched_geom:
            for candidate in ["geometry", "GEOMETRY", "geom", "shape", "SHAPE", "wkb_geometry"]:
                if candidate in available_cols:
                    matched_geom = candidate
                    break

        if matched_geom:
            geom_col = matched_geom
        
        # 1. Column selection pushdown
        if read_options.keep_columns:
            quoted_cols = [f'"{col}"' for col in read_options.keep_columns if col != geom_col]
            cols_str = ", ".join(quoted_cols) + ", " if quoted_cols else ""
        else:
            cols_str = f"* EXCLUDE ({geom_col}), "

        query = f"""
            SELECT {cols_str} ST_AsWKB({geom_col}) AS wkb_geometry 
            FROM read_parquet(?)
            WHERE 1=1
        """
        params: list[Any] = [source_path]

        # 2. Spatial filter pushdown
        sf = read_options.spatial_filter
        if sf and sf.aoi is not None and not sf.aoi.empty:
            aoi_wkt = sf.aoi.geometry.unary_union.wkt
            pred = sf.predicate.lower()

            if pred == "intersects":
                query += f" AND ST_Intersects({geom_col}, ST_GeomFromText(?))"
                params.append(aoi_wkt)
            elif pred == "within_distance" and sf.distance:
                query += f" AND ST_DWithin({geom_col}, ST_GeomFromText(?), ?)"
                params.extend([aoi_wkt, sf.distance])
            elif pred == "touches":
                query += f" AND ST_Touches({geom_col}, ST_GeomFromText(?))"
                params.append(aoi_wkt)

        # 3. Attribute filter pushdown
        where_sql = None
        if read_options.where is not None:
            where_sql = compile_where(read_options.where, dialect="sqlite")
        elif read_options.definition_query:
            where_sql = read_options.definition_query

        if where_sql:
            query += f" AND ({where_sql})"

        logger.info(f"Executing DuckDB S3 query on {source_path}")
        try:
            df = conn.execute(query, params).fetchdf()
        except Exception as exc:
            raise DataReadError(f"Failed to read Parquet from {source_path}: {exc}") from exc

        if df.empty:
            logger.warning(f"No records returned for query on {source_path}")
            cols = [c for c in df.columns if c != "wkb_geometry"]
            return gpd.GeoDataFrame(columns=cols, geometry=[], crs=source_crs)

        # 4. WKB geometry parsing
        geometries = shapely.from_wkb(df["wkb_geometry"])
        df.drop(columns=["wkb_geometry"], inplace=True)

        return gpd.GeoDataFrame(df, geometry=geometries, crs=source_crs)

    def describe(
        self, 
        *, 
        source_path: str, 
        geom_col: str = "geometry", 
        source_crs: str = "EPSG:4326", 
        **kwargs: Any
    ) -> DatasetInfo:
        conn = self._get_connection()
        schema_df = conn.execute("DESCRIBE SELECT * FROM read_parquet(?)", [source_path]).fetchdf()
        cols = schema_df["column_name"].tolist()
        attr_cols = [c for c in cols if c != geom_col]

        count_df = conn.execute("SELECT COUNT(*) AS cnt FROM read_parquet(?)", [source_path]).fetchdf()
        row_count = int(count_df["cnt"].iloc[0])

        return DatasetInfo(
            geom_column=geom_col,
            crs=source_crs,
            geometry_type="polygon",
            columns=attr_cols,
            row_count=row_count,
        )