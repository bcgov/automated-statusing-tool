# ast/ast_engine/storage/__init__.py

import os
from pathlib import Path

from .models import StorageConfig, JobStorageContext
from .s3_writer import S3ResultsStorageWriter
from .local_writer import LocalResultsStorageWriter
from .writer import ResultsStorageWriter
from ast_engine.config import settings

def create_results_writer(context: JobStorageContext) -> ResultsStorageWriter:
    backend = settings.STORAGE_TYPE

    config = StorageConfig(
        bucket=settings.RESULTS_BUCKET,
        environment=settings.RESULTS_ENV,
        prefix=settings.RESULTS_PREFIX,
        endpoint_url=settings.RESULTS_S3_ENDPOINT_URL,
        local_root=Path(settings.RESULTS_LOCAL_ROOT).resolve(),
    )

    if backend == "S3":
        return S3ResultsStorageWriter(config, context)

    if backend == "local":
        return LocalResultsStorageWriter(config, context)

    raise ValueError(f"Unsupported AST results storage backend: {backend}")