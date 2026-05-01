
# TODO: AI Generated -- needs validation

from pathlib import Path
import geopandas as gpd
from data_adapters.base import BaseSpatialAdapter, ReadOptions
from data_adapters.exceptions import DataReadError, DataCrsError


class KMLAdapter(BaseSpatialAdapter):
    """
    Adapter for KML files.
    """

    def _read_impl(
        self,
        *,
        path: str | Path,
        read_options: ReadOptions,
        layer: str | None = None,
        **_,
    ) -> gpd.GeoDataFrame:
        try:
            return gpd.read_file(path, layer=layer)
        except Exception as exc:
            raise DataReadError(f"Failed to read KML: {path}") from exc
        

