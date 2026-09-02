from fastapi import APIRouter

from models import JobCreate
from database import create_job, get_jobs

router = APIRouter()

@router.get("")
def get_all_jobs():
    jobs = get_jobs()
    return jobs

@router.get("/{job_id}/status")
def get_job_status(job_id):
    pass

@router.post("")
def add_job(job: JobCreate):
    create_job(job.status)
    return {"message": "job created"}