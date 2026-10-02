import json
from pathlib import Path

import redis
from rq import Queue
from ast_engine.config.settings import Settings

settings = Settings()

redis_client = redis.Redis(host=settings.redis_host, port=settings.redis_port, decode_responses=True)
rq_queue = Queue(settings.job_queue, connection=redis_client)

jobs_path = Path(__file__).with_name("jobs.json")

with jobs_path.open("r", encoding="utf-8") as f:
    jobs = json.load(f)

for job in jobs:
    print ("Enqueueing job:", job["user"], job["aoi_id"])
    rq_queue.enqueue("ast_api.job_management.test.process_job", job)