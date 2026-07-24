# ast/ast_engine/tests/storage/test_key_builder.py
import pytest
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Mapping

from ast_engine.storage.key_builder import ResultsKeyBuilder, JobStorageContext, StorageConfig

pytestmark = pytest.mark.unit

@pytest.fixture
def mock_config():
    return StorageConfig(
        prefix="test-prefix",
        environment="dev",
        bucket="test-bucket",
        access_id="test-key",
        access_key="test-secret",
        endpoint_url="http://localhost:9000",
        config=None,
        use_ssl=False,
    )

@pytest.fixture
def mock_context():
    return JobStorageContext(
        created_date=datetime.now(),
        job_id="test-job-123",
    )

def test_key_builder_job_prefix(mock_config, mock_context):
    builder = ResultsKeyBuilder(mock_config, mock_context)
    expected = "test-prefix/env=dev/date=2024-06-01/job_id=test-job-123"
    assert builder.job_prefix == expected

def test_key_builder_key_method(mock_config, mock_context):
    builder = ResultsKey_builder(mock_config, mock_context)
    relative_path = "data/file.parquet"
    expected = f"{builder.job_prefix}/data/file.parquet"
    assert builder.key(relative_path) == expected

def test_key_builder_uri_method(mock_config, mock_context):
    builder = ResultsKeyBuilder(mock_config, mock_context)
    relative_path = "data/file.parquet"
    expected = f"s3://test-bucket{builder.key(relative_path)}"
    assert builder.uri(relative_path) == expected


