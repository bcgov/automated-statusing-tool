from __future__ import annotations

import geopandas as gpd

from ast_engine.core.data_adapters.base import (
    BaseSpatialAdapter,
    DatasetInfo,
)


class InMemorySpatialAdapter(BaseSpatialAdapter):
    """Return controlled data and record the operator's request."""

    def __init__(
        self,
        gdf: gpd.GeoDataFrame | None = None,
    ) -> None:
        self.gdf = (
            gdf
            if gdf is not None
            else gpd.GeoDataFrame(
                geometry=[],
                crs="EPSG:3005",
            )
        )
        self.last_options = None
        self.last_target_crs = None
        self.last_source_kwargs = None

    def read(
        self,
        *,
        read_options=None,
        target_crs=None,
        **source_kwargs,
    ) -> gpd.GeoDataFrame:
        self.last_options = read_options
        self.last_target_crs = target_crs
        self.last_source_kwargs = source_kwargs

        return self.gdf.copy()

    def _read_impl(
        self,
        *,
        read_options,
        **source_kwargs,
    ) -> gpd.GeoDataFrame:
        return self.gdf.copy()

    def describe(self, **source_kwargs) -> DatasetInfo:
        raise NotImplementedError