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
    # Feature-id column names to look for, in priority order. OBJECTID should cover
    # every BCGW table and most file feature classes; FID might be the case for some shapefiles.
    # If none are present we leave unique_id unset and the operators fall back to the row index.
    ID_FIELD_CANDIDATES = ("OBJECTID", "FID")
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
    def _resolve_unique_id(self, authored: Optional[str]) -> Optional[str]:
        # Resolve the feature-id column against the real columns from describe().
        # An author-set value must be a real column - we return it in the
        # column's own casing so the operators match it exactly. When it isn't a
        # column we raise, rather than let it silently fall back to the row index
        # at run time. With no author value we default to OBJECTID / FID, or None
        # when neither is present (the operators then use the row index).
        by_upper = {c.upper(): c for c in (self.columns or [])}
        if authored:
            match = by_upper.get(authored.upper())
            if match is None:
                raise ValueError(
                    f"unique_id {authored!r} for dataset {self.base.name!r} is "
                    f"not a column of {self.base.datasource!r}. Available "
                    f"columns: {sorted(self.columns or [])}. Leave unique_id "
                    f"blank to auto-pick OBJECTID / FID."
                )
            return match
        for candidate in self.ID_FIELD_CANDIDATES:
            if candidate in by_upper:
                return by_upper[candidate]
        return None

    def build(self) -> RegistryDataset:
        '''
        Builds RegistryDataset from BaseDataset via metadata Enrichment
        '''
        data = self.base.model_dump(by_alias=True)
        # Resolve the feature id against the real columns: validate an author-set
        # value, or default to OBJECTID / FID when blank.
        data["unique_id"] = self._resolve_unique_id(data.get("unique_id"))
        return RegistryDataset(
            **data,
            id=self.id,
            columns=self.columns,
            geom_column=self.geom_column,
            geometry_type=self.geometry_type,
            crs=self.crs,
            data_adapter=self.data_adapter,
            row_count=self.row_count,
        )


