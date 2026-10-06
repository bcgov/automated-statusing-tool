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
#
# Both registries share this same block, but fill it in differently:
#   - Tab 2 (spreadsheet) sets it automatically from Buffer_Distance, so it only
#     ever produces overlay or within_distance.
#   - Tab 1 (hand-written YAML) sets it directly and can use any of the four
#     types - nearest and adjacency live here.
# The block accepts all four types from either source, so adding nearest or
# adjacency to Tab 2 in the future only means revising the spreadsheet inference
# (utils.infer_operator), not this model.

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
            # definition_query is still the primary input (the spreadsheet's
            # Definition_Query column); 'where' is derived from it below. Logged
            # at debug so the normal Tab 2 path is not noisy at build time.
            logger.debug(
                "Dataset '%s' uses definition_query; 'where' will be derived from it.",
                self.name,
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


class SkippedDataset(BaseModel):
    '''A dataset from the source spreadsheet that could not be built.

    A run carries on without it, so this is how the registry says what is not in
    it. Without this the registry just comes out short and nothing downstream can
    tell the difference between "this dataset was checked and found nothing" and
    "this dataset was never checked at all".
    '''
    name: str
    datasource: str
    # where it failed: "spreadsheet row" (the row itself could not be read, usually
    # a definition query the parser does not understand) or "reading the dataset"
    # (the table or file could not be opened, usually a path that no longer exists)
    stage: str
    reason: str


class Registry(BaseModel):
    version: str
    os:str
    date:str
    id:str
    datasets: List[RegistryDataset]
    # Datasets that are NOT in the list above, and why. Empty on a clean build.
    # Defaults to empty so registries built before this existed still load.
    skipped: List[SkippedDataset] = []


