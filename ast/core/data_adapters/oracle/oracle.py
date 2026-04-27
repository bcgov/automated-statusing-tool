from data_adapters.base import BaseSpatialAdapter
from data_adapters.exceptions import DataReadError
import geopandas as gpd

class OracleAdapter(BaseSpatialAdapter):
    """
    Oracle Spatial dataset adapter.

    This adapter is responsible for retrieving features from
    an Oracle Spatial database that intersect a provided AOI.
    It assumes all dataset metadata (CRS, geometry type,
    spatial index) has been validated prior to runtime.

    Responsibilities:
    - Construct spatially enabled queries
    - Execute queries against Oracle Spatial
    - Return results in a neutral, engine-consumable form

    """
    def read() -> gpd.geodataframe:
        pass