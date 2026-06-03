from typing import Optional, List
from pydantic import BaseModel

class BaseDataset(BaseModel):
    # Core identifiers
    id: str
    name: str
    # data definition
    datasource: str
    definition_query: Optional[str] = None
    # Aggregation
    aggregate_columns: List[str] = []


class RegistryDataset(BaseDataset):
    # Enriched metadata
    columns: List[str]
    geom_column: str
    geometry_type: str
    crs: str
    data_adapter: str
    row_count: int


class Registry(BaseModel):
    version: str
    datasets: List[RegistryDataset]


