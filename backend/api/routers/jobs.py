from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

import models
from database import get_db
from schemas import JobCreate, JobResponse

router = APIRouter()

@router.get("/", response_model=list[JobResponse], tags=["jobs"])
async def get_jobs(db: Annotated[Session, Depends(get_db)]):
    result = db.execute(select(models.Job))
    users = result.scalars().all()
    if users:
        return users
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No jobs found")

@router.post("/", response_model=JobResponse, tags=["jobs"])
async def create_job(job: JobCreate, db: Annotated[Session, Depends(get_db)]):
    result = db.execute(select(models.User).where(models.User.id == job.user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    new_job = models.Job(
        title=job.title,
        content=job.content,
        user_id=job.user_id,
    )
    db.add(new_job)
    db.commit()
    db.refresh(new_job)
    return new_job

# probably dont want to delete any jobs but have this for testing
@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(job_id: int, db: Annotated[Session, Depends(get_db)]):
    result = db.execute(select(models.Job).where(models.Job.id == job_id))
    job = result.scalars().first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    db.delete(job)
    db.commit()