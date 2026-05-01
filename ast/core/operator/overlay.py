"""
core/operator/overlay.py takes the output from AOI and overlays
it against the data described in datasets.yaml
- if this code gets big put it in its own core/overlay module
- consider a future using asynco for data reads that might have I/O latency
- minimize and optimize geometry operations
"""
from pydantic import BaseModel
from enum import Enum
from typing import Literal
import geopandas as gpd
from data_adapters.kml import KMLAdapter

class DataAdpterType(str, Enum):
    KML = "kml"
    FGDB = "fgdb"
    SHP = "shp"
    ORACLE = "oracle"
class AoiData(BaseModel):
    '''Placeholder for the real AoiData model'''
    data: gpd.GeoDataFrame

class DataModel(BaseModel):
    ''' Also a placeholder for the real datamodel for app data'''
    data_type: DataAdpterType
    data: gpd.GeoDataFrame
    query: str
    fields: list[str]
    operators: list[str]

class overlay:
    def __init__(self,aoi: AoiData,DataModel: DataModel):
        self.aoi = aoi
        self.data_model = DataModel

    def execute(self) -> gpd.GeoDataFrame:
        
        gpd.clip(self.data_model.data,self.aoi.data, )

aoi = AoiData( KMLAdapter().read('aoi.kml',target_crs="EPSG:3005"))
