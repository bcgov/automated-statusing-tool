import json
import logging
import redis
from pathlib import Path
import geopandas as gpd
from datetime import datetime, UTC

from typing import Optional
from dataclasses import dataclass

from ast_engine.core.aoi.aoi_builder import AOIBuilder, AOIRequest
from ast_engine.core.execution import run_analysis, build_tasks
from ast_engine.storage.publisher import ResultsPublisher
from ast_engine.storage import create_results_writer, JobStorageContext
from ast_engine.storage.models import OperatorArtifact
from ast_engine.config.settings import Settings

logger = logging.getLogger(__name__)

#Payload structure
@dataclass
class ast_job_payload:
    job_id: str
    registries: list[str]
    created_at: Optional[str] = None
    user: str
    aoi_id: str
    aoi_name: str
    aoi: dict


def main():
    settings = Settings()
    redis_host= settings.REDIS_HOST
    redis_port = settings.REDIS_PORT
    redis_database = settings.REDIS_DATABASE
    target_crs = settings.SYSTEM_CRS
    
    redis_client = redis.Redis(host=redis_host, port=redis_port, db=redis_database)
    queue_name = settings.AST_JOB_QUEUE

    logger.info(f"Listening for jobs on Redis queue: {queue_name}")

    while True:
        # Blocking pop from the Redis queue
        # Payload expected to be a JSON string with job details
        queue, message = redis_client.blpop(queue_name)
        
        if not message:
            continue
            
        job_payload = json.loads(message.decode('utf-8'))
        job_id = job_payload.get("job_id")
        registries = job_payload.get("registries")
        created_at = job_payload.get("created_at", datetime.now(UTC).isoformat())
        user = job_payload.get("user")
        aoi_id = job_payload.get("aoi_id")
        aoi_name = job_payload.get("aoi_name")

        logger.info(f"Picked up job: {job_id}")
        
        try:
            # Form the AOI
            # TODO: Is from features what we want to use here?Coordinate with API
            gdf = gpd.GeoDataFrame.from_features(
                job_payload["aoi"]['features'],
                crs=target_crs
            )
            request = AOIRequest(aoi_id=aoi_id, name=aoi_name, target_crs=target_crs)
            aoi = AOIBuilder().from_gdf(request, gdf)

            # TODO: Are registries a list provided by the api. 
            # Perhaps they should be appended to a base config registry
            tasks = build_tasks(registries)
            
            # engage engine
            ast_results = run_analysis(
                aoi=aoi,
                tasks=tasks,
                job_id=job_id,
            )

            # hey -- AstResults is a Pydantic model, so we can serialize it to JSON directly
            output_dir = Path(settings.temp_dir) / job_id
            output_dir.mkdir(parents=True, exist_ok=True)
            
            raw_results_file = output_dir / "raw_results.json"
            raw_results_file.write_text(ast_results.model_dump_json())
            operator_outputs = []
            for dataset_group in ast_results.results:
                for result in dataset_group.results:
                    if result.spatial_link:
                        operator_output = OperatorArtifact(registry="blablabla",operator=result.operator_type,dataset_name=dataset_group.dataset_name,path=result.spatial_link)
                        operator_outputs.append(OperatorArtifact)
            
            completed_at = datetime.now(UTC).isoformat()

            # Publisher will upload all items in the manifest paths
            storage_context = JobStorageContext(job_id=job_id,created_date=created_at)
            writer = create_results_writer(context=storage_context)
            publisher = ResultsPublisher(writer=writer)
            manifest_path = publisher.publish_job_results(
                job_id=job_id,
                user=user,
                created_at=created_at,
                completed_at=completed_at,
                execution_time=ast_results.execution_time,
                status="success",
                engine_version="1.0.0", # TODO: draw from config
                raw_results_json=raw_results_file,
                operator_outputs=
                # Include other optional paths as they become available:
                # extracted_gpkg=..., 
                # aoi_geojson=...,
            )
            
            logger.info(f"Job {job_id} completed and published. Manifest: {manifest_path}")

        except Exception as e:
            logger.exception(f"Job {job_id} failed catastrophically.")
            # TODO: Handel errors in execution and publication

if __name__ == "__main__":
    main()