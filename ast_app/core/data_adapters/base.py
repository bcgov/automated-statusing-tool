from abc import ABC, abstractmethod
import geopandas as gpd
from ast_app.core.data_adapters.exceptions import DataCrsError

from typing import Iterable


class ReadOptions:
    """
    Optional read controls applicable to all spatial adapters.

    Adapters should push these down to the source (preferred)
    or apply them post-read if needed.
    """

    def __init__(
        self,
        *,
        spatial_mask: gpd.GeoDataFrame | None = None,
        definition_query: str | None = None,
        keep_columns: Iterable[str] | None = None,
    ):
        self.spatial_mask = spatial_mask
        self.definition_query = definition_query
        self.keep_columns = list(keep_columns) if keep_columns else None



class BaseSpatialAdapter(ABC):
    """
    Source-agnostic base class for spatial adapters.
    """

    def read(
        self,
        *,
        read_options: ReadOptions | None = None,
        target_crs: str | None = None,
        **source_kwargs,
    ) -> gpd.GeoDataFrame:
        read_options = read_options or ReadOptions()

        gdf = self._read_impl(
            read_options=read_options,
            **source_kwargs,
        )

        self._validate_crs(gdf)

        if target_crs:
            gdf = self._reproject(gdf, target_crs)

        # Fallback filters (only applied if adapter didn't push down)
        gdf = self._apply_post_filters(gdf, read_options)

        return gdf

    @abstractmethod
    def _read_impl(
        self,
        *,
        read_options: ReadOptions,
        **source_kwargs,
    ) -> gpd.GeoDataFrame:
        """Adapter-specific read implementation"""

    # -----------------------------
    # Shared fallback behavior
    # -----------------------------

    def _apply_post_filters(
        self,
        gdf: gpd.GeoDataFrame,
        opts: ReadOptions,
    ) -> gpd.GeoDataFrame:
        if opts.definition_query:
            gdf = gdf.query(opts.definition_query)

        if opts.spatial_mask is not None:
            gdf = self._clip(gdf, opts.spatial_mask)

        if opts.keep_columns:
            gdf = self._select_columns(gdf, opts.keep_columns)

        return gdf

    def _clip(
        self,
        gdf: gpd.GeoDataFrame,
        mask: gpd.GeoDataFrame,
    ) -> gpd.GeoDataFrame:
        if gdf.crs != mask.crs:
            mask = mask.to_crs(gdf.crs)
        return gpd.clip(gdf, mask)

    def _select_columns(
        self,
        gdf: gpd.GeoDataFrame,
        keep: list[str],
    ) -> gpd.GeoDataFrame:
        cols = set(keep) | {gdf.geometry.name}
        return gdf[[c for c in gdf.columns if c in cols]]

    def _validate_crs(self, gdf: gpd.GeoDataFrame) -> None:
        if gdf.crs is None:
            raise DataCrsError("Input dataset has no CRS defined")

    def _reproject(self, gdf, target_crs):
        try:
            return gdf.to_crs(target_crs)
        except Exception as exc:
            raise DataCrsError from exc
