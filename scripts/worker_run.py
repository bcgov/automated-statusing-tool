import os
import json

import geopandas as gpd
import pandas as pd
from ast_engine.config.logging_config import setup_logging
from ast_engine.config.registry import utils
import orchestrator_run
from ast_engine.workers.worker import run_worker,AstJob,JobStatus
import uuid
from datetime import datetime, UTC
import logging


logger = logging.getLogger(__name__)
SAMPLE_REGISTRY=os.getenv("SAMPLE_REGISTRY")


def main():
    setup_logging()
    registry = utils.load_yaml(SAMPLE_REGISTRY)
    gdf = gpd.read_file(orchestrator_run.SHP)
    for col in gdf.columns:
        if pd.api.types.is_datetime64_any_dtype(gdf[col]):
            gdf[col] = gdf[col].astype(str)

    job = AstJob(
        job_id=uuid.uuid4(),
        registries=[('demo',registry)],
        created_at=datetime.now(UTC).isoformat(),
        user="mr.bot",
        aoi_id="12345678-90ab-cdef-1234-567890abcdef",
        aoi_name="test_aoi",
        aoi=json.loads(gdf.to_crs("EPSG:4326").to_json()),
        status= JobStatus.QUEUED,
    )
    result = run_worker(job=job, publish=False)
    logger.debug("Result: %s",result)

if __name__ == "__main__":
    main()
    import threading

    logger.info("Threads at shutdown:")
    for t in threading.enumerate():
        logger.debug("%s", t)
