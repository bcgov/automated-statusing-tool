# /shared_modules/database.py
# database for job retentiion
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from uuid import UUID
from typing import Optional, Dict, Any
from ast_api.config.settings import Settings
from orm_models import JobDBModel, JobStatus,RegistryDBModel
from models.api import DataStatus,Registry,RegistrySummary

settings = Settings()
# Determine database URL from environment variable, defaulting to a local SQLite file
# For PostgreSQL/Oracle later, this can easily be overridden via config or env (e.g., postgresql://user:pass@host/db)
DATABASE_URL = settings.database_url

# Create the SQLAlchemy engine
# Note: check_same_thread=False is only required for SQLite when accessed across multiple threads/workers
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 4. Create a Base class for your ORM models to inherit from
Base = declarative_base()
def init_db():
    """
    Import your ORM models here so Base knows about them, 
    then create all tables if they don't exist.
    """
    from shared_modules.orm_models import JobDBModel,RegistryDBModel
    Base.metadata.create_all(bind=engine)

def get_db():
    """
    Dependency generator for FastAPI routes to yield a database session 
    and ensure it closes automatically after the request finishes.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_job(db: Session, job_id: UUID, payload: Dict[str, Any]) -> JobDBModel:
    """
    Creates a new job record in the database with status QUEUED.
    Called by the FastAPI API when a user enqueues a job.
    """
    db_job = JobDBModel(
        job_id=str(job_id),
        status=JobStatus.QUEUED,
        payload=payload,
        error=None
    )
    db.add(db_job)
    db.commit()
    db.refresh(db_job)
    return db_job

def get_job(db: Session, job_id: UUID | str) -> Optional[JobDBModel]:
    """
    Retrieves a job record by its ID.
    Called by the API (for status checks) or the Worker (to fetch input payloads).
    """
    return db.query(JobDBModel).filter(JobDBModel.job_id == str(job_id)).first()

def update_job_status(
    db: Session, 
    job_id: UUID | str, 
    status: JobStatus, 
    error: Optional[str] = None
) -> Optional[JobDBModel]:
    """
    Updates the status of a job (e.g., PROCESSING, COMPLETED, FAILED) 
    and records an error message if the job failed.
    Called by the Worker during execution.
    """
    db_job = get_job(db, job_id)
    if db_job:
        db_job.status = status
        if error is not None:
            db_job.error = error
        db.commit()
        db.refresh(db_job)
    return db_job

def create_registry(db: Session, registry: Registry) -> RegistryDBModel:
    """
    Creates a new job record in the database with status QUEUED.
    Called by the FastAPI API when a user enqueues a job.
    """
    db_job = RegistryDBModel(
        name=registry.name,
        path=registry.path
        )
    db.add(db_job)
    db.commit()
    db.refresh(db_job)
    return db_job
def get_registries(db:Session)->dict:
    registries = (
        db.query(RegistryDBModel.id, RegistryDBModel.name)
        .order_by(RegistryDBModel.name)
        .all()
    )
    return [RegistrySummary(id=registry.id,name=registry.name) for registry in registries]

def get_registry(db: Session, id: UUID | str) -> Optional[RegistryDBModel]:
    """
    Retrieves a job record by its ID.
    Called by the API (for status checks) or the Worker (to fetch input payloads).
    """
    return db.query(RegistryDBModel).filter(RegistryDBModel.id == str(id)).first()

