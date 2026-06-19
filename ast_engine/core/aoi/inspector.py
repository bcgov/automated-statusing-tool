from __future__ import annotations

import logging

import geopandas as gpd
from shapely.geometry.base import BaseGeometry

from .exceptions import SpatialGeometryError
from .models import AOIProperties, AOIPart
from .utils import check_gdf, parse_crs, count_vertices, has_z, has_m

logger = logging.getLogger(__name__)


class AOIInspector:
    """
    AOI-wide snapshot properties from the normalized AOI.
    """

    def inspect(
        self,
        gdf: gpd.GeoDataFrame,
        parts: tuple[AOIPart, ...],
    ) -> AOIProperties:
        check_gdf(
            gdf,
            req_projected_crs=True,
            strict=True,
            context="Normalized AOI",
        )

        if not parts:
            raise SpatialGeometryError("Normalized AOI has no AOI parts.")

        crs = parse_crs(gdf.crs, label="Normalized AOI CRS")

        footprint = gdf.union_all()

        if footprint is None or footprint.is_empty:
            raise SpatialGeometryError(
                "Normalized AOI footprint is empty after union."
            )

        footprint_area_ha = float(footprint.area / 10_000.0)
        overlay_area_ha = float(sum(part.area_ha for part in parts))

        overlay_to_footprint_ratio = (
            overlay_area_ha / footprint_area_ha
            if footprint_area_ha > 0
            else None
        )

        vertex_counts = tuple(part.vertex_count for part in parts)

        props = AOIProperties(
            crs_epsg=crs.to_epsg(),
            crs_string=crs.to_string(),

            footprint_area_ha=footprint_area_ha,
            overlay_area_ha=overlay_area_ha,
            overlay_to_footprint_ratio=overlay_to_footprint_ratio,

            bounds=tuple(float(v) for v in footprint.bounds),

            feature_count=int(len(gdf)),
            part_count=int(len(parts)),
            geometry_type=str(footprint.geom_type),
            is_valid=bool(footprint.is_valid),

            vertex_count=int(sum(vertex_counts)),
            max_vertices_per_part=(
                int(max(vertex_counts))
                if vertex_counts
                else None
            ),

            has_z=any(part.has_z for part in parts),
            has_m=any(part.has_m for part in parts),
        )

        logger.debug(
            "AOI inspection summary | crs=%s | features=%s | parts=%s | "
            "footprint_area_ha=%.4f | overlay_area_ha=%.4f | "
            "overlay_to_footprint_ratio=%s | bounds=%s | vertices=%s | "
            "max_vertices_per_part=%s | has_z=%s | has_m=%s",
            props.crs_string,
            props.feature_count,
            props.part_count,
            props.footprint_area_ha,
            props.overlay_area_ha,
            (
                round(props.overlay_to_footprint_ratio, 6)
                if props.overlay_to_footprint_ratio is not None
                else None
            ),
            props.bounds,
            props.vertex_count,
            props.max_vertices_per_part,
            props.has_z,
            props.has_m,
        )

        return props