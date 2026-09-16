#Jordan write this today! 

from pydantic import BaseModel, ConfigDict, Field
from enum import Enum 
from typing import Literal
from dataclasses import dataclass
from typing import Optional

class Regions(str, Enum): 
    Cariboo = "Cariboo"
    KootenayBoundary = "Kootenay Boundary"
    ThompsonOkanagan = "Thompson Okanagan"
    Omineca = "Omineca"
    Northeast = "Northeast"
    Skeena = "Skeena"
    SouthCoast = "South Coast"
    WestCoast = "West Coast"



class CreateJob(BaseModel):
    job_id: str
    status: Literal["Pending", "Running", "Completed", "Failed"] = "Pending"
    user: str
    date: str
    region: Regions
    area_of_interest: str
    crown_file_number: str
    disposition_number: str
    parcel_number: str
    output_directory: str
    retain_existing_outputs: bool = False
    suppress_tab_3: bool = False
    suppress_map_creation: bool = False
    open_output_directory_on_completion: bool = False
    enable_portable_spreadsheet: bool = False

class JobQueItem (BaseModel):
    job_id: str
    registries: list[str]
    created_at: Optional[str] = None
    user: str
    aoi_id: str
    aoi_name: str
    aoi: dict

class JobPayload(BaseModel): 
    job: CreateJob
    item: JobQueItem




