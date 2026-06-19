from __future__ import annotations

import logging

import geopandas as gpd
from shapely.geometry import Polygon

from .exceptions import (
    AOIPartBuildError,
    SpatialDataError,
    DataCRSError,
    SpatialGeometryError,
)
from .models import AOIPart
from .utils import check_gdf

logger = logging.getLogger(__name__)


class AOIPartBuilder:
    """
    Builds one AOIPart per polygon part from a normalized AOI GeoDataFrame.

    Stage contract:
    - Input has already been normalized.
    - Input has already been conformed to the target projected CRS.
    - Input has already been restricted to valid polygonal geometry.
    - Output parts should each contain one Polygon geometry.
    """

    def build_parts(
        self,
        *,
        aoi_id: str,
        gdf: gpd.GeoDataFrame,
    ) -> tuple[AOIPart, ...]:
        """
        Build AOIPart objects from a normalized AOI GeoDataFrame.

        Expected lower-level spatial/data/geometry errors are wrapped as
        AOIPartBuildError so callers know the part-building stage failed.
        Unexpected errors are allowed to bubble up to the builder as unexpected.
        """
        try:
            check_gdf(
                gdf,
                req_projected_crs=True,
                strict=True,
                context="Normalized AOI for part building",
            )

            exploded = self._explode_to_singleparts(
                gdf,
                aoi_id=aoi_id,
            )

            parts = self._build_parts_from_exploded(
                exploded,
                aoi_id=aoi_id,
            )

            logger.debug(
                "AOI parts summary | aoi_id=%s | part_count=%s | total_area_ha=%.4f | "
                "total_vertices=%s | has_z=%s | has_m=%s",
                aoi_id,
                len(parts),
                sum(part.area_ha for part in parts),
                sum(part.vertex_count for part in parts),
                any(part.has_z for part in parts),
                any(part.has_m for part in parts),
            )

            return parts

        except AOIPartBuildError:
            raise

        except (
            SpatialDataError,
            DataCRSError,
            SpatialGeometryError,
        ) as exc:
            raise AOIPartBuildError(
                f"AOI part building failed for {aoi_id!r}: {exc}"
            ) from exc

    def _explode_to_singleparts(
        self,
        gdf: gpd.GeoDataFrame,
        *,
        aoi_id: str,
    ) -> gpd.GeoDataFrame:
        """
        Explode normalized polygonal AOI geometry into singlepart rows.
        """
        exploded = (
            gdf.explode(
                index_parts=True,
            )
            .reset_index(drop=True)
        )

        if exploded.empty:
            raise SpatialGeometryError(
                f"AOI {aoi_id!r} produced no parts after explode."
            )

        return exploded

    def _build_parts_from_exploded(
        self,
        exploded: gpd.GeoDataFrame,
        *,
        aoi_id: str,
    ) -> tuple[AOIPart, ...]:
        parts: list[AOIPart] = []

        for row_index, row in exploded.iterrows():
            part_index = int(row_index) + 1
            part_id = f"{aoi_id}_part_{part_index:04d}"

            geom = row.geometry

            self._check_part_geometry(
                geom,
                part_id=part_id,
            )

            part_gdf = self._single_part_gdf(
                exploded,
                row_index=int(row_index),
            )

            part = AOIPart.from_gdf(
                parent_aoi_id=aoi_id,
                part_index=part_index,
                gdf=part_gdf,
                part_id=part_id,
            )

            parts.append(part)

        if not parts:
            raise SpatialGeometryError(
                f"AOI {aoi_id!r} produced no AOI parts."
            )

        return tuple(parts)

    def _check_part_geometry(
        self,
        geom,
        *,
        part_id: str,
    ) -> None:
        if geom is None or geom.is_empty:
            raise SpatialGeometryError(
                f"AOI part {part_id!r} has null or empty geometry."
            )

        if not isinstance(geom, Polygon):
            raise SpatialGeometryError(
                f"Expected exploded AOI part {part_id!r} to be Polygon. "
                f"Got: {geom.geom_type!r}."
            )

        if not geom.is_valid:
            raise SpatialGeometryError(
                f"AOI part {part_id!r} has invalid geometry."
            )

    def _single_part_gdf(
        self,
        exploded: gpd.GeoDataFrame,
        *,
        row_index: int,
    ) -> gpd.GeoDataFrame:
        """
        Return a one-row GeoDataFrame for a single AOI part.

        Preserves any non-geometry attributes from the exploded AOI.
        """
        part_gdf = exploded.iloc[[row_index]].copy()
        part_gdf = part_gdf.set_geometry(
            exploded.geometry.name,
            crs=exploded.crs,
        )

        return part_gdf.reset_index(drop=True)