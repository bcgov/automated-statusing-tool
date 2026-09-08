from __future__ import annotations

from dataclasses import dataclass

import geopandas as gpd

from ast_engine.tests.helpers.aoi_geometry import (
    PROJECTED_CRS,
    WGS84_CRS,
    aoi_gdf,
    rect,
)


@dataclass(slots=True)
class AOIStub:
    """Minimum AOI contract needed by spatial operators."""

    gdf: gpd.GeoDataFrame
    aoi_id: str = "test_aoi"


def projected_operator_aoi() -> AOIStub:
    """Return a 2,000 m by 1,500 m rectangular AOI."""

    return AOIStub(
        gdf=aoi_gdf(
            [
                rect(
                    1_000_000,
                    1_000_000,
                    1_002_000,
                    1_001_500,
                )
            ],
            crs=PROJECTED_CRS,
        )
    )


def geographic_operator_aoi() -> AOIStub:
    """Return the operator AOI transformed to geographic coordinates."""

    projected = projected_operator_aoi()

    return AOIStub(
        gdf=projected.gdf.to_crs(WGS84_CRS),
        aoi_id=projected.aoi_id,
    )