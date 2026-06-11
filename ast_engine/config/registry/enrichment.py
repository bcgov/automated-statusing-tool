import logging
from .models import BaseDataset, RegistryDataset
from ...core.data_adapters.base import DatasetInfo
from ...core.data_adapters.file.adapter import FileSpatialAdapter
from ...core.data_adapters.oracle.adapter import OracleAdapter
from typing import Optional
import uuid

logger = logging.getLogger(__name__)

class Enrich():
    '''Enrichment class to enrich BaseDataset with additional metadata
    TODO: might be nice if enrich had parameters (version: str, dataset_list: List)
    amd returned a Registry
    '''
    # File datasources end in one of these, or carry a path; everything else is
    # a BCGW table named SCHEMA.TABLE.
    GEO_EXTENSIONS = (".gdb", ".gpkg", ".shp", ".geojson", ".kml", ".kmz")
    def __init__(self, base: BaseDataset, connection=None, cursor=None):
        # enrichment state
        self.id: Optional[str]
        self.columns: Optional[list[str]] = None
        self.geom_column: Optional[str] = None
        self.geometry_type: Optional[str] = None
        self.crs: Optional[str] = None
        self.data_adapter: Optional[str] = None
        self.row_count: Optional[int] = None
        self.base = base
        # A live BCGW connection is only needed to enrich Oracle datasets. The
        # caller opens one connection and reuses it across every dataset in the
        # build, the same way the read path does. File datasets ignore it.
        self.connection = connection
        self.cursor = cursor
    def resolve_adapter(self):
        # File datasources carry a path (slashes) or a known geo file type;
        # everything else is a BCGW table named SCHEMA.TABLE.
        ds = self.base.datasource.strip()
        if "/" in ds or "\\" in ds or ds.lower().endswith(self.GEO_EXTENSIONS):
            return "FILE"
        if "." in ds:
            return "ORACLE"
        raise ValueError(f"Could not resolve a data adapter for: {ds!r}")
    def _set_metadata(self, info: DatasetInfo):
        # Map the adapter's DatasetInfo onto the enrichment fields. The field
        # names line up 1:1, and geometry_type is already lowercase
        # ("point" / "line" / "polygon").
        self.columns = info.columns
        self.crs = info.crs
        self.geom_column = info.geom_column
        self.geometry_type = info.geometry_type
        self.row_count = info.row_count
    def enrich_from_file(self):
        # read the file's metadata without loading all of its features
        info = FileSpatialAdapter().describe(path=self.base.datasource)
        self._set_metadata(info)
    def enrich_from_oracle(self):
        # read the BCGW table's metadata over a live connection
        if self.connection is None or self.cursor is None:
            raise ValueError(
                "Enriching a BCGW (Oracle) dataset needs a live database "
                "connection. Open an OracleConnection during the build and pass "
                f"it to Enrich. Dataset: {self.base.datasource!r}"
            )
        info = OracleAdapter(self.connection, self.cursor).describe(
            table=self.base.datasource
        )
        self._set_metadata(info)
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


