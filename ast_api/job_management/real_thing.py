import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4
import sqlite3

import geopandas as gpd

from ast_engine.config.registry import utils
from ast_engine.entry.worker import AstJob, JobStatus, run_worker
from ast_api.database import create_connection 

#Some pseudo 
# Where the hell is the AOI ?? 
# Take the job id, que the db 
# Who am I? 
# If tantalis - no need to use an 'aoi' file 
# If source = 1
# What is my purpose? 

def aoi_placeholder(): 
    pass 

#will probably need to change the name of payload, but that's another story 
def process_job(payload: dict) -> dict:
    
    aoi = aoi_placeholder() #this is a placeholder for the AOI, which will be resolved from the job id and the database 
    
    registry = utils.load_yaml(Path(os.environ["REGISTRY"]))
    
    # Temporary: use one registry configured for all jobs.
    with create_connection() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM jobs WHERE job_id = ?",
            (payload.get("job_id"),),
        ).fetchone()


    if row is None:
        raise LookupError(f"Job {payload.get('job_id')} not found")

    # These require implementing AOI lookup/loading:
    # aoi_geojson = resolve_aoi(row)
    # registry = load_registry_for_job(row)

    job = AstJob(
        job_id=(row["job_id"]),
        registries=[("demo", registry)],
        created_at=row["created_at"],
        user=row["name"],
        aoi_id="2",
        aoi_name="test",
        aoi=aoi,
        status=JobStatus.QUEUED,
    )


    # The sample jobs contain a GeoJSON Feature; the engine expects
    # a FeatureCollection with a "features" list.
    aoi_geojson = payload["aoi"]
    if aoi_geojson.get("type") == "Feature":
        aoi_geojson = {
            "type": "FeatureCollection",
            "features": [aoi_geojson],
        }
    

    #Change this to be the incoming spatial from the front end 
    aoi_gdf = gpd.GeoDataFrame.from_features(aoi_geojson["features"])
    aoi_gdf = aoi_gdf.set_crs("EPSG:4326", allow_override=True)



    completed_job = run_worker(engine_job, publish=False)
    if completed_job is None:
        raise RuntimeError(f"Engine failed for AOI {payload['aoi_id']}")

    return {
        "job_id": str(completed_job.job_id),
        "aoi_id": completed_job.aoi_id,
        "status": str(completed_job.status),
    }