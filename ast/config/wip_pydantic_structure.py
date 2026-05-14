# Last modified 20260514 BMANG
# work-in-progress using pydantic to for data validation

from typing import Annotated, Literal, Optional

from annotated_types import Gt, Ge

from pydantic import BaseModel, SecretStr, ValidationError
print("imports complete")

class Geometry(BaseModel):
    # string input
    geom_column: str
    # multipart needed? curve?
    # input must be point, line, polygon
    # TO-DO make case insensitive?
    geom_type: Literal["point", "line", "polygon"]
    # input must be integer greater than 0
    crs: Annotated[int, Gt(0)]

class AdjacencyOperator(BaseModel):
    # TO-DO distance value needed?
    pass

class BufferOperator(BaseModel):
    distance: Annotated[float, Gt(0)]

class OverlayOperator(BaseModel):
    # no distance needed cause intersect
    pass

class ProximityOperator(BaseModel):
    distance: Annotated[float, Gt(0)]

class Operators(BaseModel):
    adjacent: Optional[AdjacencyOperator] = None
    buffer: Optional[BufferOperator] = None
    overlay: OverlayOperator
    proximity: Optional[ProximityOperator] = None

# class SomeOperators(BaseModel):
#     operators: dict[Literal["adjacent", "buffer", "overlay", "proximity"], Optional[Annotated[float, Gt(0)]]]

#class OperatorDistance(BaseModel):
#    distance: Optional[Annotated[float, Gt(0)]] = None

class Validate(BaseModel):
    # should this be uuid?
    #input must be integer greater than or equal to 0
    id: Annotated[int, Ge(0)]
    # string input
    name: str
    # string input
    unique_id: str
    # input must be fgdb, kml, oracle, shp
    # TO-DO make case insensitive and validate against allowed list of adapter types
    adapter_type: Literal["fgdb", "kml", "oracle", "shp"]
    # str layer or table, SecretStr for UNC paths?
    # does it need to be dict?
    # dict input
    datasource: dict[str, SecretStr]
    # optional, list of strings
    columns: Optional[list[str]] = None
    # optional, string
    definition: Optional[str] = None
    geom: Geometry
    operators: Operators

sample_dict = {
    "id": 0,
    "name": "Featureclass_Name",
    "unique_id": "OBJECTID",
    "adapter_type": "fgdb",
    "datasource": {
        "layer": "Datasource"
    },
    "columns": [
        "Fields_to_Summarize",
        "Fields_to_Summarize2",
        "Fields_to_Summarize3",
        "Fields_to_Summarize4",
        "Fields_to_Summarize5",
        "Fields_to_Summarize6",
    ],
    "geom": {
        "geom_column": "GEOMETRY",
        "geom_type": "point",
        "crs": 4326
    },
    "operators": {"overlay": {},
                  "buffer": {"distance": 50}
    }
}
#print(sample_dict)
try:
    # load via kwargs
    test = Validate(**sample_dict)
    print(test)
except ValidationError as e:
    print(e.errors())
