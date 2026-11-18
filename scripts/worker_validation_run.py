import os
import json
from pathlib import Path
import sys

import geopandas as gpd
import pandas as pd
import uuid
from datetime import datetime, UTC
import logging

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[1]

from ast_engine.config.logging_config import setup_logging
from ast_engine.config.registry import utils
from ast_engine.entry.worker import run_worker, AstJob, JobStatus
from ast_engine.config.settings import Settings

# Shared models
from shared_models.models import Regions


DATA_DIR = REPO_ROOT / "ast_engine" / "tests" / "data"
SHP = DATA_DIR / "Test_Shape_A" / "Test_Shape_A_shp" / "Test_Shape_A.shp"  # the AOI box
# SHP = DATA_DIR / "Test_Data_District_shp" / "dqu.shp"  # the AOI box
SAMPLE_REGISTRY = REPO_ROOT / os.getenv("SAMPLE_REGISTRY")


def main():
    settings = Settings()
    registry = utils.load_yaml(SAMPLE_REGISTRY)
    gdf = gpd.read_file(SHP)
    for col in gdf.columns:
        if pd.api.types.is_datetime64_any_dtype(gdf[col]):
            gdf[col] = gdf[col].astype(str)

    job = AstJob(
        job_id=uuid.uuid4(),
        region=Regions.Cariboo,
        registries=[('demo',registry)],
        created_at=datetime.now(UTC).isoformat(),
        user="mr.bot",
        aoi_id="12345678-90ab-cdef-1234-567890abcdef",
        aoi_name="test_aoi",
        aoi=json.loads(gdf.to_crs("EPSG:4326").to_json()),
        status= JobStatus.QUEUED,
    )
    logger.info("Job: %s", job)

    result = run_worker(job=job, publish=False)
    logger.debug("Result: %s",result)

if __name__ == "__main__":
    setup_logging()
    main()
    import threading

    logger.info("Threads at shutdown:")
    for t in threading.enumerate():
        logger.debug("%s", t)