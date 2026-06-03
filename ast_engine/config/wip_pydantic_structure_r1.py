# work-in-progress, outline of flow:
# spreadsheet class to
# intermediate model to
# enrichment to
# full data model to yaml?

# %% imports

from typing import Annotated, Literal, Optional

from annotated_types import Gt, Ge

from pydantic import BaseModel, Field, computed_field, model_validator

# %% class definitions

class ExcelClass(BaseModel):
    category: str
    name: str
    datasource: str
    definition: Optional[str] = None
    buffer_distance: Optional[Annotated[float, Gt(0)]] = None
    sum_field_1: Optional[str] = Field(default=None, exclude=True)
    sum_field_2: Optional[str] = Field(default=None, exclude=True)
    sum_field_3: Optional[str] = Field(default=None, exclude=True)
    sum_field_4: Optional[str] = Field(default=None, exclude=True)
    sum_field_5: Optional[str] = Field(default=None, exclude=True)
    sum_field_6: Optional[str] = Field(default=None, exclude=True)
    #sum_field_6: Optional[str] = None
    #map_label = Optional[str] = None

class IntermediateClass(ExcelClass):
    #columns: Optional[list[str]] = None
    # summarize columns and return list or None
    @computed_field
    @property
    def columns(self) -> Optional[list[str]]:
        values = [
            self.sum_field_1,
            self.sum_field_2,
            self.sum_field_3,
            self.sum_field_4,
            self.sum_field_5,
            self.sum_field_6
        ]
        # ignore None values, add rest to list
        filtered = [v for v in values if v is not None]
        return filtered if filtered else None

class EnrichmentClass(IntermediateClass):
    # TO-DO get adapter, verify file path, get schema?

    # computed field won't validate against the Literal options
    #def adapter_type(self) -> Literal["fgdb", "kml", "oracle", "shp"]:
    @computed_field
    @property
    def adapter_type(self) -> str:
        # TO-DO some kind of validation to get adapter type
        # don't think this is very robust...
        # go back to pathlib if we're opening files?
        # dictionary with adapters
        file_ext = {".gdb": "fgdb", ".shp": "shp", ".kml": "kml", ".kmz": "kml"}
        for key, value in file_ext.items():
            if key in self.datasource:
                return value
        # check if text uppercase
        if self.datasource.isupper():
            return "oracle"
        # if none of the above return unknown
        # should we throw an error or write unknown to yaml?
        return "unknown"
    
    # TO-DO for EnrichmentClass
    # validate file path
    # get unique id field
    # verify if summary fields exist?
    # get geometry column, srid, etc
# %% sample output

# test_2 = IntermediateClass(category="Cumulative Effects - Caribou", name="Caribou Recovery Partnership Zones", datasource = r"Mtn_Caribou_Draft_Partnership_Agreement_June_2021.gdb\Partnership_Agreement_Proposed_June_2021", sum_field_1="ZONE", sum_field_6="Detail")
# test_2.model_dump()
# {'category': 'Cumulative Effects - Caribou',
#  'name': 'Caribou Recovery Partnership Zones',
#  'datasource': 'Mtn_Caribou_Draft_Partnership_Agreement_June_2021.gdb\\Partnership_Agreement_Proposed_June_2021',
#  'definition': None,
#  'buffer_distance': None,
#  'columns': ['ZONE', 'Detail'],
#  'adapter_type': 'fgdb'}
# test_2.model_dump(exclude_none=True)
# {'category': 'Cumulative Effects - Caribou',
#  'name': 'Caribou Recovery Partnership Zones',
#  'datasource': 'Mtn_Caribou_Draft_Partnership_Agreement_June_2021.gdb\\Partnership_Agreement_Proposed_June_2021',
#  'columns': ['ZONE', 'Detail'],
#  'adapter_type': 'fgdb'}


# def get_adapter(file_path):
#     # handles windows and linux paths
#     path = PureWindowsPath(file_path)
#     #linux_path = path.as_posix()
    
#     #path_parts = [part.lower() for part in path.parts]
#     if path.match("*.gdb/*"):
#         return "gdb"
#     elif path.full_match("*.*"):
#         return "oracle"
#     elif path.suffix:
#         return path.suffix.lower()[1:]
#     else:
#         return "unknown"
