from __future__ import annotations

from dataclasses import dataclass

import geopandas as gpd

from .exceptions import AOIValidationError
from .models import AOIPart


class AOIPartBuilder:
    """
    Explodes the normalized AOI into one AOIPart per polygon part.
    """

    def build_parts(self, aoi_id: str, gdf: gpd.GeoDataFrame) -> tuple[AOIPart, ...]:
        exploded = gdf.explode(index_parts=True).reset_index(drop=True)

        parts: list[AOIPart] = []

        for idx, row in exploded.iterrows():
            geom = row.geometry

            if geom is None or geom.is_empty:
                raise AOIValidationError(f"AOI part {aoi_id}_part_{idx + 1} has empty geometry")

            if geom.geom_type != "Polygon":
                raise AOIValidationError(f"Expected exploded AOI part to be Polygon, got {geom.geom_type!r}")

            parts.append(
                AOIPart(
                    part_id=f"{aoi_id}_part_{idx + 1}",
                    parent_aoi_id=aoi_id,
                    geom_type=geom.geom_type,
                    part_index=idx + 1,
                    gdf=gpd.GeoDataFrame([row]),
                    bounds=tuple(float(v) for v in geom.bounds),
                    area_ha=float(geom.area / 10_000.0),
                )
            )

        return tuple(parts)