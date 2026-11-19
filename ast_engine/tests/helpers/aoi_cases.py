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

def projected_execution_aoi() -> AOIStub:
    """Return a rectangular AOI from the bounds of data/Test_Shape_A.shp.
       This is the AOI used in the execution tests, which aligns with existing file.
       based input data. The AOI is 3,595 m by 3,343 m in BC Albers (EPSG:3005).
    """

    return AOIStub(
        gdf=aoi_gdf(
            [
            rect(
                1_331_637.5494999997,
                713_157.9225999992,
                1_335_232.2644999996,
                716_501.1124000009,
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