"""
FileSpatialAdapter
Reads spatial features from a local file and returns a GeoDataFrame.

Handles every GDAL supportedfile format the AST takes as input: shapefile,
file geodatabase, GeoPackage, GeoJSON, KML and KMZ. They are all read through
gpd.read_file(): GDAL picks the right driver from the file extension, so one
adapter covers them all.
"""

from pathlib import Path

import geopandas as gpd

from ..base import BaseSpatialAdapter, ReadOptions, SpatialFilter
from ..exceptions import DataReadError


class FileSpatialAdapter(BaseSpatialAdapter):
    """Adapter for local spatial files (SHP, FGDB, GeoPackage, GeoJSON, KML, KMZ).

    `path` points at the file. `layer` is needed for container formats that
    hold more than one layer (file geodatabase, GeoPackage). single-layer files like
    shapefile and GeoJSON do not need it.

    When ReadOptions carries a SpatialFilter, the AOI bounding box is pushed
    down to gpd.read_file() so GDAL only returns features near the AOI instead
    of reading the whole file (much more efficient). The push-down is a coarse pre-filter (bounding
    box level) - the operator still does the exact spatial test afterwards.
    """

    def _read_impl(
        self,
        *,
        path: str | Path,
        read_options: ReadOptions,
        layer: str | None = None,
        **_,
    ) -> gpd.GeoDataFrame:
        """Read the file, pushing the AOI bounding box down to GDAL."""
        bbox = self._build_bbox(read_options.spatial_filter)
        try:
            gdf = gpd.read_file(path, layer=layer, bbox=bbox)
        except Exception as exc:
            raise DataReadError(f"Failed to read spatial file: {path}") from exc
        return gdf

    def _build_bbox(
        self,
        spatial_filter: SpatialFilter | None,
    ) -> gpd.GeoSeries | None:
        """Turn a SpatialFilter into a bounding box for gpd.read_file().

        Returned as a GeoSeries (carries its CRS) so geopandas reprojects
        it to the dataset's CRS before filtering. Returns None when there is
        nothing to push down.

        bbox creation is predicate dependent:
          - intersects / touches -> the AOI itself
          - within_distance      -> the AOI buffered by the search distance,
                                    so features just outside the AOI are kept
          - nearest              -> no filter. the closest feature can be
                                    anywhere, so the whole file is read
        """
        if spatial_filter is None or spatial_filter.predicate == "nearest":
            return None

        if spatial_filter.predicate == "within_distance":
            aoi = spatial_filter.aoi
            if not aoi.crs.is_projected:
                raise DataReadError(
                    "within_distance push-down needs a projected AOI CRS "
                    "(the search distance is measured in metres)"
                )
            return aoi.buffer(spatial_filter.distance)

        # intersects / touches
        return spatial_filter.aoi.geometry
