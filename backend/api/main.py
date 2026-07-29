# uv run fastapi dev backend/api/main.py

from fastapi import FastAPI

from models import JobCreate
from database import create_table, create_job, get_jobs

app = FastAPI()

create_table()

@app.get("/", include_in_schema=False, name="home")
def home():
    return {"message": "Hello world!"}

@app.get("/api/users/{user_id}/jobs")
def get_user_jobs(user_id):
    pass

@app.post("/api/users")
def add_user():
    pass

@app.get("/api/jobs")
def get_all_jobs():
    jobs = get_jobs()
    return jobs

@app.get("/api/jobs/{job_id}/status")
def get_job_status(job_id):
    pass

@app.post("/api/jobs")
def add_job(job: JobCreate):
    create_job(job.status)
    return {"message": "job created"}

# from https://github.com/bcgov/burn-severity-map/blob/main/backend/api/main.py
@app.get("/health", include_in_schema=False, summary="Health Check", tags=["Monitoring"])
async def health_check():
    return {"message": "Hello world!"}

@app.get("/health/api")
def api_health():
    #version= os.getenv('APP_VERSION', 'dev')
    return {'status': 'ok',
            'version': 1.1}