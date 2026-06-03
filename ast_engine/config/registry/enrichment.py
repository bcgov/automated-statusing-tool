import logging
from models import BaseDataset, RegistryDataset
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)

class Enrich():
    FILE_TYPES=['.gdb','.shp']
    def __init__(self, base: BaseDataset):
        # enrichment state
        self.columns: Optional[list[str]] = None
        self.geom_column: Optional[str] = None
        self.geometry_type: Optional[str] = None
        self.crs: Optional[str] = None
        self.data_adapter: Optional[str] = None
    def resolve_adapter(self):
        if self.base.datasource.upper().startswith("WHSE"):
            self.data_adapter = "ORACLE"
        else:
            ds =Path(self.base.datasource)
            if ds.suffix.lower() in self.FILE_TYPES:
                return 'FILE'
            else:
                for part in ds.parts:
                    if part.lower() in self.FILE_TYPES:
                        return 'FILE'
                raise ValueError('Datasource data adapter could not be resolved')  
    def enrich_from_file(self):
        # use the file data adapter to get this info
        self.columns = ['FOO','BAR']
        self.crs = 'EPSG:3005'
        self.geom_column = 'GEOMETRY'
        self.geometry_type = 'POLYGON'
    def enrich_from_oracle(self):
        # use the oracle data adapter to get this info
        self.columns = ['FOO','BAR']
        self.crs = 'EPSG:3005'
        self.geom_column = 'GEOMETRY'
        self.geometry_type = 'POLYGON'
    def enrich(self):
        '''Resolves data adapter and enriches object with metadata'''
        self.data_adapter = self.resolve_adapter()
        if self.data_adapter == 'FILE':
            self.enrich_from_file()
        elif self.data_adapter == 'ORACLE':
            self.enrich_from_oracle()
        else:
            raise ValueError('Datasource data adapter could not be resolved')    
    def build(self) -> RegistryDataset:
        '''
        Builds RegistryDataset from BaseDataset via metadata Enrichment
        '''
        
        return RegistryDataset(
            **self.base.model_dump(),
            columns=self.columns,
            geom_column=self.geom_column,
            geometry_type=self.geometry_type,
            crs=self.crs,
            data_adapter=self.data_adapter,
        )


