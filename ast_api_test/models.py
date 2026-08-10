from __future__ import annotations

from pydantic import BaseModel


class Jobs(BaseModel):
    __tablename__ = "jobs"

    id: int
    title: str
    description: str
    spatial_file: str | None = None
