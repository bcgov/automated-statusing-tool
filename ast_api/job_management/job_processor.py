
def process_job(job):
    print("Processing job:", job["user"], job["aoi_id"])
    return {
        "status": "queued",
        "user": job["user"],
        "aoi_id": job["aoi_id"],
    }