from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class JobsBase(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1)
    spatial_file: str | None = None


class JobsCreate(JobsBase):
    pass


class JobsResponse(JobsBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    date_posted: str