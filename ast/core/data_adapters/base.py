from abc import ABC,abstractmethod
import geopandas as gpd

class BaseSpatialAdapter(ABC):
    """
    Abstract base class for all spatial data adapters.
    Every adapter must have the methods in contained here
    """

    @abstractmethod
    def read(self, **kwargs) -> gpd.GeoDataFrame:
        """
        Read spatial dataset and return a GeoDataFrame
        Every implementation must:
        - return a valid GeoDataFrame
        - Set or transform CRS
        - Raise exeptions on failure
        """
        raise NotImplementedError