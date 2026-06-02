# work-in-progress, flow:
# spreadsheet class
# intermediate model / enrichment?
# full data model

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
    @computed_field
    @property
    # computed field won't validate against the Literal options
    #def adapter_type(self) -> Literal["fgdb", "kml", "oracle", "shp"]:
    def adapter_type(self) -> str:
        # TO-DO some kind of validation to get adapter type    
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
    
    # TO-DO
    # validate file path
    # get unique id field
    # get geometry column, srid, etc
# %%
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
