# ast/ast_engine/tests/storage/test_s3_writer.py
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch
from ast_engine.storage.key_builder import StorageConfig, JobStorageContext
from ast_engine.storage.s3_writer import S3ResultsStorageWriter

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

@patch('boto3.client')
def test_s3_writer_init(mock_client, mock_config, mock_context):
    writer = S3ResultsStorageWriter(mock_config, mock_context)
    mock_client.assert_called_once_with(
        's3',
        aws_access_key_id='test-key',
        aws_secret_access_key='test-secret',
        endpoint_url='http://localhost:9000',
        config=None,
        use_ssl=False
    )

@patch('boto3.client')
def test_s3_writer_put_file(mock_client, mock_config, mock_context, tmpdir):
    mock_client.return_value = MagicMock()
    local_path = tmpdir.join("test_file.txt")
    with open(local_path, "w") as f:
        f.write("test content")
    
    relative_key = "data/file.txt"
    content_type = "text/plain"
    metadata = {"test": "data"}
    
    writer = S3ResultsStorageWriter(mock_config, mock_context)
    writer.put_file(local_path, relative_key, content_type, metadata)
    
    mock_client.return_value.upload_file.assert_called_once_with(
        Filename=str(local_path),
        Bucket='test-bucket',
        Key=f"{writer.keys.key(relative_key)}",
        ExtraArgs={'ContentType': 'text/plain', 'Metadata': {'test': 'data'}}
    )

@patch('boto3.client')
def test_s3_writer_put_text(mock_client, mock_config, mock_context):
    mock_client.return_value = MagicMock()
    relative_key = "data/file.txt"
    content = "test text content"
    content_type = "text/plain"
    metadata = {"test": "data"}
    
    writer = S3ResultsStorageWriter(mock_config, mock_context)
    writer.put_text(content, relative_key, content_type, metadata)
    
    mock_client.return_value.put_object.assert_called_once_with(
        Bucket='test-bucket',
        Key=f"{writer.keys.key(relative_key)}",
        Body=content.encode('utf-8'),
        ContentType='text/plain',
        Metadata={'test': 'data'}
    )