
import json
import redis


def _get_all_jobs(db: redis.Redis) -> list[dict]:
    raw_jobs = db.lrange("jobs_queue", 0, -1)
    return [json.loads(j) for j in raw_jobs]