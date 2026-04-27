
# TODO: AI Generated -- needs validation

from pathlib import Path
import geopandas as gpd
from data_adapters.base import BaseSpatialAdapter
from data_adapters.exceptions import DataReadError, DataCrsError


class KMLAdapter(BaseSpatialAdapter):
    """
    Adapter for KML files.
    - read kml
    - return crs compliant gdf
    """

    def read(
        self,
        path: str | Path,
        layer: str | None = None,
        target_crs: str | None = None,
    ) -> gpd.GeoDataFrame:
        try:
            gdf = gpd.read_file(path, layer=layer)
        except Exception as exc:
            raise DataReadError(f"Failed to read KML: {path}") from exc

        # KML is usually WGS84, but be defensive
        if gdf.crs is None:
            raise DataCrsError
        if target_crs:
            gdf = gdf.to_crs(target_crs)

        return gdf
