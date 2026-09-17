from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

class UserBase(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    email: EmailStr = Field(max_length=120)

# dont want to return anything
class UserCreate(UserBase):
    pass

# public response to API
class UserResponse(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int

class UserUpdate(BaseModel):
    username: str | None = Field(default=None, min_length=1, max_length=50)
    email: EmailStr | None = Field(default=None, max_length=120)

class JobBase(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1)

class JobCreate(JobBase):
    user_id: int  # TEMPORARY, eventually want to retrieve using SSO?    

class JobResponse(JobBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    date_created: datetime
    owner: UserResponse    