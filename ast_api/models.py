#Jordan write this today! 

from pydantic import BaseModel, ConfigDict, Field
from enum import Enum 
from typing import Literal

## inputs to AST are: 
# Region 
# Area of Interest 
# Crown File Number:>
# Disposition Number
# Parcel Number 
# Output Directory.


# Check boxes ??
# Retain Existing Outputs (Restart Analysis)
# Supress Tab 3 (Constraints)
# Supress Map Creation (Tab 3)
# Open Output Directory on Completion? 
# Enable Portable Spreadsheet? 

class Regions(str, Enum): 
    Cariboo = "Cariboo"
    KootenayBoundary = "Kootenay Boundary"
    ThompsonOkanagan = "Thompson Okanagan"
    Omineca = "Omineca"
    Northeast = "Northeast"
    Skeena = "Skeena"
    SouthCoast = "South Coast"
    WestCoast = "West Coast"


class CreateJobs(BaseModel):
    '''
    This Model is used to normalize the inputs from the user that gets sent to the back end
    '''
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


class JobDatabase(BaseModel):
    '''
    This model is used in SQLLite to hold job information. 
    Might be superflous, but there are things that should not be done in the User Model. 
    The functionality could technical be extended.
    '''
    job_id: str
    region: Regions
    area_of_interest: str
    crown_file_number: str
    disposition_number: str
    parcel_number: str
    output_directory: str
    status: Literal["Pending", "Running", "Completed", "Failed"]
