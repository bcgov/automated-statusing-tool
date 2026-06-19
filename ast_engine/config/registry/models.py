from typing import Optional, List, Union, Literal, Annotated
from pydantic import BaseModel,model_validator,field_validator,Field
from .query import WhereClause, LogicalGroup,definition_to_where

import logging
logger = logging.getLogger(__name__)


# --- Operator block --------------------------------------------------------
# Per dataset: which analysis to run and the parameters it needs. The "type"
# decides which parameters are valid:
#   overlay          -> no parameters
#   within_distance  -> distance_m
#   nearest          -> k (+ optional max_distance_m)
#   adjacency        -> tolerance_m
# These four type names match the orchestrator's analysis names and the
# operator functions one-to-one (overlay.intersection,
# proximity.within_distance, proximity.nearest, adjacent.adjacency).

class OverlaySpec(BaseModel):
    type: Literal["overlay"] = "overlay"


class WithinDistanceSpec(BaseModel):
    type: Literal["within_distance"] = "within_distance"
    distance_m: float


class NearestSpec(BaseModel):
    type: Literal["nearest"] = "nearest"
    k: int = 1
    max_distance_m: Optional[float] = None


class AdjacencySpec(BaseModel):
    type: Literal["adjacency"] = "adjacency"
    tolerance_m: float = 0.0


# the "type" value picks the matching spec above
OperatorSpec = Annotated[
    Union[OverlaySpec, WithinDistanceSpec, NearestSpec, AdjacencySpec],
    Field(discriminator="type"),
]


class BaseDataset(BaseModel):
    # Core identifiers
    name: str
    # data definition
    datasource: str
    definition_query: Optional[str] = None
    # Aggregation
    aggregate_columns: List[str] = []
    
    # added
    where: Optional[WhereClause | LogicalGroup] = None

    # Which analysis to run + its parameters. Tab 2 fills this from the
    # Buffer_Distance column at build time; the Tab 1 YAML sets it directly / hardcoded for now.
    operator: Optional[OperatorSpec] = None

    # Name of the column that uniquely identifies a feature (e.g. OBJECTID /
    # FID). Normally left blank by the author and filled in during enrichment;
    # None means the operators fall back to the row index.
    unique_id: Optional[str] = None

    # early ensure aggregate_columns is a list
    @field_validator("aggregate_columns", mode="before")
    @classmethod
    def ensure_list(cls, v):
        if isinstance(v, str):
            return [v]
        return v

    @model_validator(mode="after")
    def normalize_where(self):

        if self.where is None and self.definition_query:
            logger.warning(
                f"[Future Deprecation] Dataset '{self.name}' uses definition_query. "
                "Future versions Please migrate to 'where'."
            )

        # correct type → do nothing
        if isinstance(self.where, (WhereClause, LogicalGroup)):
            return self

        # call parser
        if self.definition_query:
            self.where = definition_to_where(self.definition_query)

        return self



class RegistryDataset(BaseDataset):
    # Enriched metadata
    id: str
    columns: List[str]
    geom_column: str
    geometry_type: str
    crs: str
    data_adapter: str
    row_count: int


class Registry(BaseModel):
    version: str
    datasets: List[RegistryDataset]


