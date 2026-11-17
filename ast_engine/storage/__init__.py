# ast/ast_engine/storage/__init__.py

import logging
from pathlib import Path

from .models import StorageConfig, JobStorageContext, RAW_RESULTS_KEY
from .s3_writer import S3ResultsStorageWriter
from .local_writer import LocalResultsStorageWriter
from .writer import ResultsStorageWriter
from .s3_reader import S3ResultsStorageReader
from .local_reader import LocalResultsStorageReader
from .reader import ResultsStorageReader
from ast_engine.config.settings import Settings


def created_date(created_at: str | None) -> str:
    """The YYYY-MM-DD date a job's results are filed under.

    A job carries the full timestamp it was created at; the storage path only
    wants the day. Taking the date part here, in one place, is what keeps the
    worker that writes the results and the API that reads them on the same path.
    A full timestamp must not go into the path: it holds colons, which are not
    allowed in a Windows file name.
    """
    if not created_at:
        raise ValueError("A job needs a created_at timestamp to locate its results")
    return created_at[:10]


def _storage_config(settings: Settings) -> StorageConfig:
    """The storage settings shared by the results writer and the results reader."""
    return StorageConfig(
        bucket=settings.results_s3_bucket,
        access_id=settings.results_s3_access_id,
        access_key=settings.results_s3_key,
        environment=settings.environment,
        prefix=settings.results_prefix,
        endpoint_url=settings.results_s3_endpoint_url,
        local_root=Path(settings.results_local_root).resolve(),
        use_ssl = settings.s3_use_ssl,
    )


def create_results_writer(context: JobStorageContext) -> ResultsStorageWriter:
    settings = Settings()
    logger = logging.getLogger(__name__)    
    backend = settings.storage_type

    config = _storage_config(settings)
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


def create_results_reader(context: JobStorageContext) -> ResultsStorageReader:
    """Build the reader for the storage backend the writer published to."""
    settings = Settings()
    backend = settings.storage_type

    config = _storage_config(settings)

    if backend == "S3":
        return S3ResultsStorageReader(config, context)

    if backend == "local":
        return LocalResultsStorageReader(config, context)

    raise ValueError(f"Unsupported AST results storage backend: {backend}")
