from __future__ import annotations

from typing import Any, Optional, Tuple
import geopandas as gpd
from dataclasses import dataclass

from .models import AOIProperties, AOIPart
from .exceptions import AOIGeometryError, DataCRSError


class AOIInspector:
    """
    AOI-wide snapshot properties from the normalized AOI.
    """

    def inspect(
        self,
        gdf: gpd.GeoDataFrame,
        parts: tuple[AOIPart, ...],

    ) -> AOIProperties:
        if gdf.empty:
            raise AOIGeometryError("Cannot inspect an empty AOI")

        if gdf.crs is None:
            raise DataCRSError("Cannot inspect AOI without a CRS")

        epsg = gdf.crs.to_epsg()
        if epsg is None:
            raise DataCRSError("AOI CRS did not resolve to an EPSG code")

        geom = gdf.union_all()
        
        return AOIProperties(
            crs_epsg=int(epsg),
            footprint_area_ha=float(geom.area / 10_000.0), # unioned footprint area (landbase coverage)
            bounds=tuple(float(v) for v in geom.bounds),

            # From parts builder
            part_count=int(len(parts)), # Individual polygon parts in AOIParts
            overlay_area_ha=float(sum(p.area_ha for p in parts)), # Spatial analysis coverage area
        )