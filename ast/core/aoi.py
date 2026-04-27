"""
This will contain the functionality for dealing with AOI's
If code base growns >~400 lines move to /aoi and make it a module
- read the aoi with appropriate data adapter 
- apply validation rules
- return a gdf that meets a predictable format for the overlay

TODO: implement /utilities/ for spatial data type detection?

"""

# EM
# Dropping in a basic example of an AOI dataclass schema
import geopandas as gpd

#@dataclass
class AreaOfInterest:
    aoi_id: str
    name: str
    gdf: gpd.GeoDataFrame
    buffer_dist: int = 0

    def __post_init__(self):
        if self.gdf.crs is None:
            raise ValueError(f"AOI {self.aoi_id} has no CRS defined")

    def is_projected(self) -> bool:
        return self.gdf.crs and self.gdf.crs.is_projected

    @property
    def crs(self):
        return self.gdf.crs

    @property
    def buffered_gdf(self) -> gpd.GeoDataFrame:
        if self.buffer_dist and not self.is_projected():
            raise ValueError("Buffering requires a projected CRS")
        gdf = self.gdf.copy()
        if self.buffer_dist:
            gdf["geometry"] = gdf.geometry.buffer(self.buffer_dist)
        return gdf

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        return tuple(self.buffered_gdf.total_bounds)
