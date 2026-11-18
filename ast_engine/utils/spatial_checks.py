from __future__ import annotations

import geopandas as gpd
from numpy import isfinite
from pyproj import CRS

from ast_engine.core.exceptions import SpatialDataError, DataCRSError, SpatialGeometryError

POLYGONAL_TYPES = {"Polygon", "MultiPolygon"}


def check_polygon_frame(
    gdf: gpd.GeoDataFrame,
    *,
    label: str,
    allow_empty: bool = False,
    require_metric: bool = True,
) -> None:
    """Check the frame, then every polygon. Empty references still need metadata."""
    check_frame(gdf, label=label, allow_empty=allow_empty)
    if require_metric:
        require_projected_metres(gdf.crs, label=f"{label} CRS")
    if gdf.empty:
        return

    geometry = gdf.geometry
    check_polygon_rows(geometry, label=label)
    areas = (geom.area for geom in geometry)
    if any(not isfinite(area) or area <= 0 for area in areas):
        raise SpatialGeometryError(f"{label} must have finite, positive polygon areas.")

    
def check_frame(
    gdf: gpd.GeoDataFrame, *, label: str, allow_empty: bool = False
) -> None:
    """Require an active geometry column and a declared CRS; leave rows alone."""
    if gdf is None:
        raise SpatialDataError(f"{label} is None.")
    if not isinstance(gdf, gpd.GeoDataFrame):
        raise SpatialDataError(
            f"{label} must be a GeoDataFrame. Got: {type(gdf).__name__}."
        )
    if gdf.empty and not allow_empty:
        raise SpatialDataError(f"{label} is empty.")

    try:
        geometry = gdf.geometry
    except AttributeError as exc:
        raise SpatialGeometryError(f"{label} has no active geometry column.") from exc
    if not isinstance(geometry, gpd.GeoSeries):
        raise SpatialGeometryError(f"{label} must have an active geometry column.")
    if geometry.crs is None:
        raise DataCRSError(f"{label} has no CRS.")


def require_projected_metres(crs: CRS, *, label: str) -> None:
    """Check the two horizontal axes before treating areas as square metres."""
    if not crs.is_projected:
        raise DataCRSError(f"{label} must be projected. Got: {crs.to_string()}.")
    axes = crs.axis_info[:2]
    if len(axes) != 2 or any(axis.unit_conversion_factor != 1.0 for axis in axes):
        raise DataCRSError(
            f"{label} must use metres on both horizontal axes. Got: {crs.to_string()}."
        )


def check_polygon_rows(geometry: gpd.GeoSeries, *, label: str) -> None:
    """The original strict row checks: null, empty, polygon type, and validity."""
    null_count = int(geometry.isna().sum())
    if null_count:
        raise SpatialGeometryError(
            f"{label} contains {null_count} null geometry record(s)."
        )
    empty_count = int(geometry.is_empty.sum())
    if empty_count:
        raise SpatialGeometryError(
            f"{label} contains {empty_count} empty geometry record(s)."
        )

    types = geometry.geom_type
    non_polygonal = types[~types.isin(("Polygon", "MultiPolygon"))]
    if not non_polygonal.empty:
        found = sorted(non_polygonal.unique())
        raise SpatialGeometryError(
            f"{label} must contain only polygonal geometry. Found: {found}."
        )
    invalid_count = int((~geometry.is_valid).sum())
    if invalid_count:
        raise SpatialGeometryError(
            f"{label} contains {invalid_count} invalid geometry record(s)."
        )


def get_geometry_column_name(
    gdf: gpd.GeoDataFrame,
    *,
    context: str,
) -> str:
    try:
        geometry_col = gdf.geometry.name
    except Exception as exc:
        raise SpatialGeometryError(
            f"{context} has no active geometry column."
        ) from exc

    if not geometry_col:
        raise SpatialGeometryError(
            f"{context} has no active geometry column."
        )

    return str(geometry_col)
    

def parse_crs(
    value: str | int | CRS,
    *,
    label: str,
) -> CRS:
    try:
        return CRS.from_user_input(value)
    except Exception as ex:
        raise DataCRSError(
            f"Invalid {label}: {value!r}. Error: {ex}"
        ) from ex
