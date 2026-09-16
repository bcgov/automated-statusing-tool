# ast/ast_engine/storage/__init__.py

import logging
from pathlib import Path

from .models import StorageConfig, JobStorageContext
from .s3_writer import S3ResultsStorageWriter
from .local_writer import LocalResultsStorageWriter
from .writer import ResultsStorageWriter
from ast_engine.config.settings import Settings
from ast_engine.config.logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)
settings = Settings()

def create_results_writer(context: JobStorageContext) -> ResultsStorageWriter:
    backend = settings.storage_type

    config = StorageConfig(
        bucket=settings.results_s3_bucket,
        access_id=settings.results_s3_access_id,
        access_key=settings.results_s3_key,
        environment=settings.environment,
        prefix=settings.results_prefix,
        endpoint_url=settings.results_s3_endpoint_url,
        local_root=Path(settings.results_local_root).resolve(),
        use_ssl = settings.s3_use_ssl,
    )
    logger.info(
        "S3 endpoint=%s access_key=%s bucket=%s",
        settings.results_s3_endpoint_url,
        settings.results_s3_access_id,
        settings.results_s3_bucket,
    )

    if backend == "S3":
        return S3ResultsStorageWriter(config, context)

    if backend == "local":
        return LocalResultsStorageWriter(config, context)

    raise ValueError(f"Unsupported AST results storage backend: {backend}")