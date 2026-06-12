import logging
from .models import BaseDataset, RegistryDataset
from typing import Optional
from pathlib import Path, PureWindowsPath
import uuid

logger = logging.getLogger(__name__)

class Enrich():
    '''Enrichment class to enrich BaseDataset with additional metadata
    TODO: might be nice if enrich had parameters (version: str, dataset_list: List)
    amd returned a Registry
    '''
    FILE_TYPES=['.gdb','.shp']
    def __init__(self, base: BaseDataset):
        # enrichment state
        self.id: Optional[str]
        self.columns: Optional[list[str]] = None
        self.geom_column: Optional[str] = None
        self.geometry_type: Optional[str] = None
        self.crs: Optional[str] = None
        self.data_adapter: Optional[str] = None
        self.row_count: Optional[int] = None
        self.base = base
    def resolve_adapter(self):
        # resolve the data adapter based on the datasource
        if self.base.datasource.upper().startswith("WHSE"):
            return "ORACLE"
        else:
            ds = PureWindowsPath(self.base.datasource)
            if ds.suffix.lower() in self.FILE_TYPES:
                return 'FILE'
            else:
                if any(part.endswith(ext) for part in ds.parts for ext in self.FILE_TYPES):
                    return 'FILE'
                # for part in ds.parts:
                #     for FILE_TYPE in self.FILE_TYPES:
                #         if FILE_TYPE in part.lower():
                #             return 'FILE'
                raise ValueError('Datasource data adapter could not be resolved')  
    def enrich_from_file(self):
        # use the file data adapter to get this info
        self.columns = ['FOO','BAR']
        self.crs = 'EPSG:3005'
        self.geom_column = 'GEOMETRY'
        self.geometry_type = 'POLYGON'
        self.row_count = 200
    def enrich_from_oracle(self):
        # use the oracle data adapter to get this info
        self.columns = ['FOO','BAR']
        self.crs = 'EPSG:3005'
        self.geom_column = 'GEOMETRY'
        self.geometry_type = 'POLYGON'
        self.row_count = 400
    def enrich(self):
        '''Resolves data adapter and enriches object with metadata'''
        # TODO: Do we need to somehow enforce unique? or move this up to the 
        # hydration level or Registry object level to ensure unique
        self.id = str(uuid.uuid4())
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
            **self.base.model_dump(by_alias=True),
            id=self.id,
            columns=self.columns,
            geom_column=self.geom_column,
            geometry_type=self.geometry_type,
            crs=self.crs,
            data_adapter=self.data_adapter,
            row_count=self.row_count,
        )


