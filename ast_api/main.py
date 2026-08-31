#main to run the fastapi backend connection to the ast_engine
import json

import redis
from fastapi import Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from ast_api.models import CreateJobs, JobDatabase, Regions
from starlette.exceptions import HTTPException as StarletteHTTPException

redis_client=redis.Redis(host='localhost', port=6379, decode_responses=True)

def get_db(): 
    yield redis_client

app = FastAPI()

templates = Jinja2Templates(directory="templates")


# Helper function to avoid code duplication
def _get_all_jobs(db: redis.Redis) -> list[dict]:
    raw_jobs = db.lrange("jobs_queue", 0, -1)
    return [json.loads(j) for j in raw_jobs]


@app.get("/", include_in_schema=False, name="home")
def home(request: Request, db: redis.Redis = Depends(get_db)):

    # get the json and put in back into a python object
    jobs = _get_all_jobs(db)

    # return the jobs list
    return templates.TemplateResponse(
        request,
        "home.html",
        {"jobs": jobs, "title": "Home"},
    )


@app.get("/jobs", include_in_schema=False, name="jobs")
def jobs_list(request: Request, db: redis.Redis = Depends(get_db)):
    jobs = _get_all_jobs(db)
    return templates.TemplateResponse(
        request,
        "jobs.html",
        {"jobs": jobs, "title": "Jobs"},
    )


@app.post("/jobs", include_in_schema=False)
def submit_job(
    request: Request,
    region: str = Form(...),
    area_of_interest: str = Form(...),
    crown_file_number: str = Form(...),
    disposition_number: str = Form(...),
    parcel_number: str = Form(...),
    output_directory: str = Form(...),
    retain_existing_outputs: bool = Form(False),
    suppress_tab_3: bool = Form(False),
    suppress_map_creation: bool = Form(False),
    open_output_directory_on_completion: bool = Form(False),
    enable_portable_spreadsheet: bool = Form(False),
    db: redis.Redis = Depends(get_db),
):
    payload = CreateJobs(
        region=Regions(region),
        area_of_interest=area_of_interest,
        crown_file_number=crown_file_number,
        disposition_number=disposition_number,
        parcel_number=parcel_number,
        output_directory=output_directory,
        retain_existing_outputs=retain_existing_outputs,
        suppress_tab_3=suppress_tab_3,
        suppress_map_creation=suppress_map_creation,
        open_output_directory_on_completion=open_output_directory_on_completion,
        enable_portable_spreadsheet=enable_portable_spreadsheet,
    )

    job = create_job(payload, db)
    return templates.TemplateResponse(
        request,
        "home.html",
        {"jobs": _get_all_jobs(db), "title": "Home", "created_job": job.model_dump()},
    )

#route for getting specific jobs
@app.get("/jobs/{job_id}", include_in_schema=False)
def job_page(request: Request, job_id: str, db: redis.Redis = Depends(get_db)):
    # get all items from the redis queue with lrange
    jobs = _get_all_jobs(db)

    for job in jobs:
        if str(job.get("job_id")) == str(job_id):
            return templates.TemplateResponse(
                request,
                "jobs.html",
                {"job": job, "description": job.get("area_of_interest", "")},
            )
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")


@app.post(
    "/api/jobs",
    response_model=JobDatabase,
    status_code=status.HTTP_201_CREATED,
)
def create_job(job: CreateJobs, db: redis.Redis = Depends(get_db)):
    jobs = _get_all_jobs(db)

    existing_ids = [
        int(j["job_id"]) for j in jobs if isinstance(j, dict) and "job_id" in j and str(j["job_id"]).isdigit()
    ]
    new_id = max(existing_ids, default=0) + 1

    new_job = {
        "job_id": str(new_id),
        "region": job.region.value,
        "area_of_interest": job.area_of_interest,
        "crown_file_number": job.crown_file_number,
        "disposition_number": job.disposition_number,
        "parcel_number": job.parcel_number,
        "output_directory": job.output_directory,
        "status": "Pending",
    }

    # Persist directly into the Redis queue
    db.rpush("jobs_queue", json.dumps(new_job))
    return JobDatabase.model_validate(new_job)


@app.get("/api/jobs", response_model=list[JobDatabase])
def get_jobs(db: redis.Redis = Depends(get_db)):
    return [JobDatabase.model_validate(job) for job in _get_all_jobs(db)]


@app.get("/api/jobs/{job_id}", response_model=JobDatabase)
def get_job(job_id: str, db: redis.Redis = Depends(get_db)):
    jobs = _get_all_jobs(db)

    for job in jobs:
        if str(job.get("job_id")) == str(job_id):
            return JobDatabase.model_validate(job)
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


