#Jordan write this today! 

from pydantic import BaseModel, ConfigDict, Field


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

class CreateJobs(BaseModel):
    region: str 
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
    job_id: str
    region: str 
    area_of_interest: str
    crown_file_number: str
    disposition_number: str
    parcel_number: str
    output_directory: str



##Need to talk to the group about this - I think that the api will only have TWO routes
# One for the job, and one for the results 
class JobResults(BaseModel):
    job_id: str
    status: str
    message: str
    output_directory: str