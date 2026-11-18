from __future__ import annotations

import logging
from math import isfinite

import geopandas as gpd

from ast_engine.utils.spatial_checks import parse_crs, check_polygon_frame
from ast_engine.core.exceptions import (
    SpatialGeometryError,
    SpatialDataError,
)
from .exceptions import (
    AOIInspectionError
)
from .models import AOIProperties, AOIPart

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
        try:
            check_polygon_frame(
                gdf,
                label="Normalized AOI",
                require_metric=True
            )

            if not parts:
                raise SpatialGeometryError("Normalized AOI has no AOI parts.")

            crs = parse_crs(gdf.crs, label="Normalized AOI CRS")

            footprint = gdf.union_all()

            if footprint is None or footprint.is_empty:
                raise SpatialGeometryError(
                    "Normalized AOI footprint is empty after union."
                )

            # Area checks
            footprint_area_ha = float(footprint.area / 10_000.0)
            parts_area_ha = float(sum(part.area_ha for part in parts))

            if any(
                not isfinite(area) or area <= 0
                for area in (footprint_area_ha, parts_area_ha)
            ):
                raise SpatialGeometryError(
                    "AOI parts and footprint areas must be finite and positive."
                )
            
            parts_to_footprint_ratio = parts_area_ha / footprint_area_ha

            vertex_counts = tuple(part.vertex_count for part in parts)

            props = AOIProperties(
                crs_epsg=crs.to_epsg(),
                crs_string=crs.to_string(),
                footprint_area_ha=footprint_area_ha,
                parts_area_ha=parts_area_ha,
                parts_to_footprint_ratio=parts_to_footprint_ratio,
                bounds=tuple(float(v) for v in footprint.bounds),
                feature_count=int(len(gdf)),
                part_count=int(len(parts)),
                geometry_type=self._resolve_geometry_type(gdf),
                vertex_count=int(sum(vertex_counts)),
                max_vertices_per_part=int(max(vertex_counts)),
                has_z=any(part.has_z for part in parts),
                has_m=any(part.has_m for part in parts),
            )

        except AOIInspectionError:
            raise

        except (
            SpatialDataError,
        ) as exc:
            raise AOIInspectionError(
                f"Failed to inspect normalized AOI properties.: {exc}"
            ) from exc

        logger.debug(
            "AOI inspection summary | crs=%s | features=%s | parts=%s | "
            "footprint_area_ha=%.4f | parts_area_ha=%.4f | "
            "parts_to_footprint_ratio=%s | bounds=%s | vertices=%s | "
            "max_vertices_per_part=%s | has_z=%s | has_m=%s",
            props.crs_string,
            props.feature_count,
            props.part_count,
            props.footprint_area_ha,
            props.parts_area_ha,
            (
                round(props.parts_to_footprint_ratio, 6)
                if props.parts_to_footprint_ratio is not None
                else None
            ),
            props.bounds,
            props.vertex_count,
            props.max_vertices_per_part,
            props.has_z,
            props.has_m,
        )

        return props
    

    @staticmethod
    def _resolve_geometry_type(gdf: gpd.GeoDataFrame) -> str:
        """Resolve the geometry type of the AOI, or return a mixed type string."""
        geom_types = tuple(sorted(set(gdf.geometry.geom_type)))

        if not geom_types:
            raise SpatialGeometryError(
                "Normalized AOI has no geometry types to inspect."
            )

        if len(geom_types) == 1:
            return geom_types[0]

        return "Mixed[" + ", ".join(geom_types) + "]"