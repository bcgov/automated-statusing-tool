import json
from datetime import datetime

import redis
from database import get_db
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from schemas import JobsCreate, JobsResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")


# Helper function to avoid code duplication
def _get_all_jobs(db: redis.Redis) -> list[dict]:
    raw_jobs = db.lrange("jobs_queue", 0, -1)
    return [json.loads(j) for j in raw_jobs]


@app.get("/", include_in_schema=False, name="home")
@app.get("/jobs", include_in_schema=False, name="jobs")
def home(request: Request, db: redis.Redis = Depends(get_db)):

    # get the json and put in back into a python object
    jobs = _get_all_jobs(db)

    # return the jobs list
    return templates.TemplateResponse(
        request,
        "home.html",
        {"jobs": jobs, "title": "Home"},
    )


@app.get("/jobs/{job_id}", include_in_schema=False)
def job_page(request: Request, job_id: int, db: redis.Redis = Depends(get_db)):
    # get all items from the redis que with lrange

    # get the json and put in back into a python object
    jobs = _get_all_jobs(db)

    for job in jobs:
        if job.get("id") == job_id:
            description = job.get("description", "")
            return templates.TemplateResponse(
                request,
                "post.html",
                {"job": job, "description": description},
            )
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")


@app.post(
    "/api/jobs",
    response_model=JobsResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_job(job: JobsCreate, db: redis.Redis = Depends(get_db)):
    jobs = _get_all_jobs(db)
    new_id = max((j["id"] for j in jobs if "id" in j), default=0) + 1

    new_job = {
        "id": new_id,
        "title": job.title,
        "description": job.description,
        "date_posted": datetime.now().strftime("%B %d, %Y")
    }

    # Persist directly into the Redis queue
    db.rpush("jobs_queue", json.dumps(new_job))
    return new_job


@app.get("/api/jobs", response_model=list[JobsResponse])
def get_jobs(db: redis.Redis = Depends(get_db)):

    return _get_all_jobs(db)


@app.get("/api/jobs/{job_id}", response_model=JobsResponse)
def get_job(job_id: int, db: redis.Redis = Depends(get_db)):

    # get the json and put in back into a python object
    jobs = _get_all_jobs(db)

    for job in jobs:
        if job.get("id") == job_id:
            return job
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")


@app.exception_handler(StarletteHTTPException)
def general_http_exception_handler(request: Request, exception: StarletteHTTPException):
    message = (
        exception.detail
        if exception.detail
        else "An error occurred. Please check your request and try again."
    )

    if request.url.path.startswith("/api"):
        return JSONResponse(
            status_code=exception.status_code,
            content={"detail": message},
        )

    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "status_code": exception.status_code,
            "title": exception.status_code,
            "message": message,
        },
        status_code=exception.status_code,
    )


@app.exception_handler(RequestValidationError)
def validation_exception_handler(request: Request, exception: RequestValidationError):
    if request.url.path.startswith("/api"):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": exception.errors()},
        )

    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "status_code": status.HTTP_422_UNPROCESSABLE_ENTITY,
            "title": status.HTTP_422_UNPROCESSABLE_ENTITY,
            "message": "Invalid request. Please check your input and try again.",
        },
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
    )
