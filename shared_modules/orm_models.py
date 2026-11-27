from sqlalchemy import Column, String, JSON, Enum
from models.models import Base

class JobDBModel(Base):
    __tablename__ = "jobs"
    job_id = Column(String, primary_key=True)
    status = Column(String, default="QUEUED")
    payload = Column(JSON)          # Stores the full input request (AOI, registries, etc.)
    error = Column(String, nullable=True)