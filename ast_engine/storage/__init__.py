# ast/ast_engine/storage/__init__.py

import os
from pathlib import Path

from .models import StorageConfig, JobStorageContext
from .s3_writer import S3ResultsStorageWriter
from .local_writer import LocalResultsStorageWriter
from .writer import ResultsStorageWriter
from ast_engine.config import settings

def create_results_writer(context: JobStorageContext) -> ResultsStorageWriter:
    backend = settings.AST_RESULTS_STORAGE_BACKEND

    config = StorageConfig(
        bucket=settings.AST_RESULTS_BUCKET,
        environment=settings.AST_RESULTS_ENV,
        prefix=settings.AST_RESULTS_PREFIX,
        endpoint_url=settings.AST_RESULTS_S3_ENDPOINT_URL,
        local_root=Path(settings.AST_RESULTS_LOCAL_ROOT).resolve(),
    )

    if backend == "s3":
        return S3ResultsStorageWriter(config, context)

    if backend == "local":
        return LocalResultsStorageWriter(config, context)

    raise ValueError(f"Unsupported AST results storage backend: {backend}")