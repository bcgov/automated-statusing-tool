'''
This module defines the authoritative structure of summary results produced
by the runtime engine. It is responsible for assembling, validating, and
serializing execution outputs into a predictable, schema-conformant form.
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
    measure: float|None = None

class OperatorType(str, Enum):
    LINE_OVERLAY = "line_overlay"
    POINT_OVERLAY = "point_overlay"
    POLYGON_OVERLAY = "polygon_overlay"
    ADJACENCY = "adjacency"
    PROXIMITY = "proximity"

class BaseOperatorResult(BaseModel):
    # Do not instantiate directly; use operator‑specific subclasses.
    analysis_timestamp: datetime = Field(default_factory=partial(datetime.now,tz=UTC))
    operator_type: OperatorType
    features: List[FeatureRecord] = Field(default_factory=list)
    # path to the saved spatial output; set by the orchestrator, not the operator
    spatial_link: str | None = None
    @computed_field
    def feature_count(self) -> int:
        return len(self.features)
    @computed_field
    def measure_value(self) -> float:
        """Returns the primary numeric result"""
        return float(self.feature_count) # Default for point/generic data
    @computed_field
    def measure_unit(self) -> str:
        """Returns the unit of measurement."""
        return "count"

class AdjacencyResult(BaseOperatorResult):
    operator_type: Literal[OperatorType.ADJACENCY] = OperatorType.ADJACENCY
    is_adjacent: bool
    @computed_field
    def measure_value(self) -> float:
        """Total shared boundary length in metres (sum of per-feature measures)."""
        return float(sum(f.measure for f in self.features if f.measure is not None))
    @computed_field
    def measure_unit(self) -> str:
        return "meters"

class PointOverlayResult(BaseOperatorResult):
    operator_type: Literal[OperatorType.POINT_OVERLAY] = OperatorType.POINT_OVERLAY

class LineOverlayResult(BaseOperatorResult):
    operator_type: Literal[OperatorType.LINE_OVERLAY] = OperatorType.LINE_OVERLAY
    total_length: float
    @computed_field
    def measure_value(self) -> float:
        return self.total_length
    @computed_field
    def measure_unit(self) -> str:
        return "meters"

class PolyOverlayResult(BaseOperatorResult):
    operator_type: Literal[OperatorType.POLYGON_OVERLAY] = OperatorType.POLYGON_OVERLAY
    total_area: float
    @computed_field
    def measure_value(self) -> float:
        return self.total_area
    @computed_field
    def measure_unit(self) -> str:
        return "square meters"
    
class ProximityResult(BaseOperatorResult):
    operator_type: Literal[OperatorType.PROXIMITY] = OperatorType.PROXIMITY
    @computed_field
    def measure_value(self) -> float:
        """Nearest distance in metres (smallest per-feature measure)."""
        distances = [f.measure for f in self.features if f.measure is not None]
        return float(min(distances)) if distances else 0.0
    @computed_field
    def measure_unit(self) -> str:
        return "meters"

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
