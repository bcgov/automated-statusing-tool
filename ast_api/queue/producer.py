import json
from pathlib import Path

import redis
from rq import Queue

redis_client = redis.Redis(host="localhost", port=6379, decode_responses=True)
rq_queue = Queue("ast-rq", connection=redis_client)

jobs_path = Path(__file__).with_name("jobs.json")

with jobs_path.open("r", encoding="utf-8") as f:
    jobs = json.load(f)

for job in jobs:
    print ("Enqueueing job:", job["user"], job["aoi_id"])
    rq_queue.enqueue("ast_api.job_processor.process_job", job)