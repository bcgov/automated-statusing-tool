from pathlib import Path
import geopandas as gpd
from ..base import BaseSpatialAdapter, ReadOptions
from ..exceptions import DataReadError, DataCrsError

class KMLAdapter(BaseSpatialAdapter):
    """
    Adapter for KML files. 
    Uses the BaseSpatialAdapter to handle most things
    Anything specific to KML reading will be overwritten by the 
    _read_impl method in this specific class 
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
        

