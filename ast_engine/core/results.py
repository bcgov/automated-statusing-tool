'''
This module defines the authoritative structure of summary results produced
by the runtime engine. It is responsible for assembling, validating, and
serializing execution outputs into a predictable, schema-conformant form.
'''
from datetime import datetime, UTC
from enum import Enum
from uuid import UUID
from functools import partial
from typing import List, Union, Literal, Annotated, Dict
from pydantic import BaseModel, Field, computed_field, ConfigDict
import geopandas as gpd
import pandas as pd

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
    registry: str | None = None
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

class AOIPartResult(BaseModel):
    """One dataset's result for one part of the AOI.

    A part is one ROW of the AOI, as the AOI's dissolve rule left it
    (AreaOfInterest.gdf):
      - full_union (the default): everything is dissolved into one row, so the
        whole AOI is one part;
      - by_fields: one row, so one part, per value of the dissolve field(s);
      - preserve_features: one row, so one part, per input feature.
    A row that is a multipart polygon stays ONE part - users think of it as one
    area. (This is not the AOI module's AOIPart, which is a single polygon used
    for the AOI checks.)

    The dataset is read once for the whole AOI, then its features are measured
    against each part on its own.

    part_attributes are the row's own attribute values, e.g. the dissolve field
    value that names the part ("A"). Empty for full_union, which keeps no
    attributes.

    Adding the parts up: when the parts do not overlap, the per-part area, length
    and shared-border totals add up to the figure for the whole AOI. Feature
    counts do not - a feature that crosses two parts is counted once in each.
    With allow_overlaps=True the parts can overlap, so area and length inside an
    overlap are counted twice.

    nearest is not split: it returns one entry for the whole AOI, with
    part_index 0 (real parts are numbered from 1) and aoi_part_id set to the
    AOI id.
    """
    aoi_part_id: str
    part_index: int
    part_area_ha: float
    part_attributes: Dict[str, str|int|float] = Field(default_factory=dict)
    result: AnalysisResult

def part_result(aoi, position: int, result) -> AOIPartResult:
    """Wrap an operator result with the AOI part (row) it was measured against.

    aoi is the AreaOfInterest and position is the row's position in aoi.gdf
    (0 for the first row). Parts are numbered from 1: <aoi id>_part_1, _part_2...
    """
    row = aoi.gdf.iloc[position]
    geometry_column = aoi.gdf.geometry.name

    # The row's own attributes, e.g. the dissolve field value that names the part.
    # Numbers and text are kept as they are, anything else (dates...) as text.
    attributes = {}
    for column, value in row.drop(labels=[geometry_column]).to_dict().items():
        if value is None or pd.isna(value):
            continue
        if isinstance(value, (int, float, str)):
            attributes[column] = value
        else:
            attributes[column] = str(value)

    return AOIPartResult(
        aoi_part_id=f"{aoi.aoi_id}_part_{position + 1}",
        part_index=position + 1,
        part_area_ha=float(row[geometry_column].area / 10_000.0),
        part_attributes=attributes,
        result=result,
    )

class OperatorOutcome(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    status: Literal["success", "failure"]
    # one entry per AOI part (nearest: one entry for the whole AOI)
    parts: List[AOIPartResult] = Field(default_factory=list)
    # each part's matched features, keyed by aoi_part_id, for the orchestrator to
    # save; carried here only, never serialized
    dataframes: Dict[str, gpd.GeoDataFrame] = Field(default_factory=dict)

class DatasetResultGroup(BaseModel):
    dataset_id: str
    dataset_name: str
    # did this dataset run? set by the orchestrator, not the operator. Tells a
    # dataset that failed apart from one that ran and found nothing - both come
    # back with no features.
    status: Literal["success", "failure"] = "success"
    # why it failed; empty when the dataset ran
    error: str | None = None
    # one entry per AOI part; empty when the dataset failed
    parts: List[AOIPartResult]

class AstResults(BaseModel):
    job_id: UUID
    aoi_id: str
    results: List[DatasetResultGroup]
    execution_time: float | None = None
