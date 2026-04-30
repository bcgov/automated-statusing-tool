'''
This module defines the authoritative structure of summary results produced
by the runtime engine. It is responsible for assembling, validating, and
serializing execution outputs into a predictable, schema-conformant form
'''
from datetime import datetime, UTC
from enum import Enum
from functools import partial
from typing import List, Union, Literal, Annotated, Dict
from pydantic import BaseModel, Field, computed_field

class FeatureRecord(BaseModel):
    # non-spatial record
    feature_id: str
    properties: Dict[str, str|int|float] = Field(default_factory=dict)

class OperatorType(str, Enum):
    LINE_OVERLAY = "line_overlay"
    POINT_OVERLAY = "point_overlay"
    POLYGON_OVERLAY = "polygon_overlay"
    ADJACENCY = "adjacency"
    PROXIMITY = "proximity"

class BaseOperatorResult(BaseModel):
    analysis_timestamp: datetime = Field(default_factory=partial(datetime.now,tz=UTC))
    operator_type: OperatorType

class AdjacencyResult(BaseOperatorResult):
    operator_type: Literal[OperatorType.ADJACENCY] = OperatorType.ADJACENCY
    is_adjacent: bool
    shared_boundary_length_m: float
    neighbor_features: List[FeatureRecord]

class OverlayResult(BaseOperatorResult):
    features: List[FeatureRecord]
    # path used to link to spatial data record
    spatial_link: str
    @computed_field
    def feature_count(self) -> int:
        return len(self.features)
    @property
    def measure_value(self) -> float:
        """Returns the primary numeric result"""
        return float(self.feature_count) # Default for point/generic data
    @property
    def measure_unit(self) -> str:
        """Returns the unit of measurement."""
        return "count"

class PointOverlayResult(BaseOperatorResult):
    operator_type: Literal[OperatorType.POINT_OVERLAY] = OperatorType.POINT_OVERLAY
    
class LineOverlayResult(OverlayResult):
    operator_type: Literal[OperatorType.LINE_OVERLAY] = OperatorType.LINE_OVERLAY
    total_length: float
    @property
    def measure_value(self) -> float:
        return self.total_length_m
    @property
    def measure_unit(self) -> str:
        return "meters"

class PolyOverlayResult(OverlayResult):
    operator_type: Literal[OperatorType.POLYGON_OVERLAY] = OperatorType.POLYGON_OVERLAY
    total_area: float
    @property
    def measure_value(self) -> float:
        return self.total_area
    @property
    def measure_unit(self) -> str:
        return "square meters"
    
class ProximityResult(BaseOperatorResult):
    operator_type: Literal[OperatorType.PROXIMITY] = OperatorType.PROXIMITY
    nearest_feature_distance: float
    nearest_feature: FeatureRecord

AnalysisResult = Annotated[
    Union[PointOverlayResult, LineOverlayResult, PolyOverlayResult, AdjacencyResult, ProximityResult],
    Field(discriminator="operator_type")
]
class DatasetResultGroup(BaseModel):
    dataset_id: str
    dataset_name: str
    results: List[AnalysisResult]

class AstResults(BaseModel):
    job_id: str
    aoi_id: str
    results: List[DatasetResultGroup]

# Example useage: TODO: Delete this prior to merge
aoi_intersect_with_data = PolyOverlayResult(
    total_area=145.8,
    features=[FeatureRecord(feature_id='12345',properties={'featureid':'12345','tenure_purpose':'License of Occupation'}),
              FeatureRecord(feature_id='12346',properties={'featureid':'12346','tenure_purpose':'License of Occupation'})],
    spatial_link="RESULT_CROWN_TENURES_TA"
    )

aoi_distance_to_data = ProximityResult(
    nearest_feature_distance=45, 
    nearest_feature=FeatureRecord(feature_id='688159',properties={'featureid':'688159','PID':'054687212','parcel_class':'Private'}))
# Combine results
all_data_results = DatasetResultGroup(dataset_id='99',dataset_name='WHSE_GSS_DATA.MANY_SMALL_POLYGONS_SV',results=[aoi_intersect_with_data,aoi_distance_to_data])
aoi_result = AstResults(job_id= 'ez_1', 
                        aoi_id='aoi_1', 
                        aoi_area_sqm=354.2,
                        results=[all_data_results] )
print (aoi_result.model_dump_json(indent=2))