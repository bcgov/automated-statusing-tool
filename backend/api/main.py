from fastapi import FastAPI

import models
from database import Base, engine, get_db
from routers import jobs, users

Base.metadata.create_all(bind=engine)

app = FastAPI()

app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])
app.include_router(users.router, prefix="/api/users", tags=["users"])

@app.get("/", include_in_schema=False, name="home")
async def home():
    return {"message": "Hello world!"}