from typing import Optional, List, Union
from pydantic import BaseModel,model_validator,field_validator
from .query import WhereClause, LogicalGroup,definition_to_where

import logging
logger = logging.getLogger(__name__)

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


