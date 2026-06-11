from typing import Optional, List, Union
from pydantic import BaseModel,model_validator
from .query import WhereClause, LogicalGroup, Condition,definition_to_where

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
    
    @model_validator(mode="after")
    def normalize_where(self):
        if self.where is None and self.definition_query:
            logger.warning(
                f"[Future Deprecation] Dataset '{self.name}' uses definition_query. "
                "Future versions Please migrate to 'where'."
            )

        # Already canonical → do nothing
        if self.where is not None:
            return self

        # Derive from legacy field
        if self.definition_query:
            parsed = definition_to_where(self.definition_query)

            if isinstance(parsed, dict):
                logic_key = list(parsed.keys())[0]  # "and" or "or"
                conditions = parsed[logic_key]

                # ✅ FIX: use alias name ("and"/"or"), not "and_"/"or_"
                self.where = LogicalGroup(
                    **{
                        logic_key: [
                            WhereClause(
                                conditions=[Condition(**c)]
                            )
                            for c in conditions
                        ]
                    }
                )

            elif isinstance(parsed, list):
                self.where = WhereClause(
                    conditions=[Condition(**c) for c in parsed]
                )

            else:
                raise ValueError("Unsupported where structure from parser")

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


