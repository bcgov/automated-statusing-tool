# ast/ast_engine/storage/__init__.py

import os
from pathlib import Path

from .models import StorageConfig, JobStorageContext
from .s3_writer import S3ResultsStorageWriter
from .local_writer import LocalResultsStorageWriter
from .writer import ResultsStorageWriter


def create_results_writer(context: JobStorageContext) -> ResultsStorageWriter:
    backend = os.getenv("AST_RESULTS_STORAGE_BACKEND", "local").lower()

    config = StorageConfig(
        bucket=os.getenv("AST_RESULTS_BUCKET", "local-ast-results"),
        environment=os.getenv("AST_RESULTS_ENV", "dev"),
        prefix=os.getenv("AST_RESULTS_PREFIX", "ast-results"),
        endpoint_url=os.getenv("AST_RESULTS_S3_ENDPOINT_URL"),
        region_name=os.getenv("AWS_REGION", "ca-central-1"),
        local_root=Path(os.getenv("AST_RESULTS_LOCAL_ROOT", "./.ast-results")).resolve(),
    )

    if backend == "s3":
        return S3ResultsStorageWriter(config, context)

    if backend == "local":
        return LocalResultsStorageWriter(config, context)

    raise ValueError(f"Unsupported AST results storage backend: {backend}")