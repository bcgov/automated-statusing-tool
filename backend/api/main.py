# uv run fastapi dev backend/api/main.py

from fastapi import FastAPI

from models import JobCreate
from database import create_table

from routers import jobs

app = FastAPI()

create_table()

app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])

@app.get("/", include_in_schema=False, name="home")
def home():
    return {"message": "Hello world!"}

@app.get("/api/users/{user_id}/jobs")
def get_user_jobs(user_id):
    pass

@app.post("/api/users")
def add_user():
    pass


# from https://github.com/bcgov/burn-severity-map/blob/main/backend/api/main.py
@app.get("/health", include_in_schema=False, summary="Health Check", tags=["Monitoring"])
async def health_check():
    return {"message": "Hello world!"}

@app.get("/health/api")
def api_health():
    #version= os.getenv('APP_VERSION', 'dev')
    return {'status': 'ok',
            'version': 1.1}