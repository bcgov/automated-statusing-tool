import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import geopandas as gpd

from ast_engine.config.registry import utils
from ast_engine.workers.worker import AstJob, JobStatus, run_worker


def process_job(payload: dict) -> dict:
    # Temporary: use one registry configured for all jobs.
    registry = utils.load_yaml(Path(os.environ["SAMPLE_REGISTRY"]))

    # The sample jobs contain a GeoJSON Feature; the engine expects
    # a FeatureCollection with a "features" list.
    aoi_geojson = payload["aoi"]
    if aoi_geojson.get("type") == "Feature":
        aoi_geojson = {
            "type": "FeatureCollection",
            "features": [aoi_geojson],
        }

    aoi_gdf = gpd.GeoDataFrame.from_features(aoi_geojson["features"])
    aoi_gdf = aoi_gdf.set_crs("EPSG:4326", allow_override=True)

    engine_job = AstJob(
        job_id=uuid4(),
        registries=[("demo", registry)],
        created_at=datetime.now(UTC).isoformat(),
        user=payload["user"],
        aoi_id=payload["aoi_id"],
        aoi_name=payload["aoi_name"],
        aoi=json.loads(aoi_gdf.to_json()),
        status=JobStatus.QUEUED,
    )

    completed_job = run_worker(engine_job, publish=False)
    if completed_job is None:
        raise RuntimeError(f"Engine failed for AOI {payload['aoi_id']}")

    return {
        "job_id": str(completed_job.job_id),
        "aoi_id": completed_job.aoi_id,
        "status": str(completed_job.status),
    }