from pydantic import BaseModel

class JobCreate(BaseModel):
    status: str