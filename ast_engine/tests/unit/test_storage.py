import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from ast_engine.storage.checksums import sha256_file, write_sha256_sidecar
from ast_engine.storage.key_builder import ResultsKeyBuilder
from ast_engine.storage.local_writer import LocalResultsStorageWriter
from ast_engine.storage.manifest import ArtifactRecord, JobManifest
from ast_engine.storage.models import JobStorageContext, StorageConfig
from ast_engine.storage.publisher import ResultsPublisher


@pytest.fixture
def storage_config(tmp_path: Path) -> StorageConfig:
    return StorageConfig(
        bucket="test-bucket",
        environment="dev",
        prefix="ast-results",
        local_root=tmp_path,
    )


@pytest.fixture
def storage_context() -> JobStorageContext:
    return JobStorageContext(
        job_id="job-12345",
        created_date="2026-03-31",
    )


# ============================================================================
# 1. Checksums Tests
# ============================================================================
@pytest.mark.unit
def test_sha256_file(tmp_path: Path):
    test_file = tmp_path / "hello.txt"
    test_file.write_text("hello world", encoding="utf-8")

    # Known sha256 for "hello world"
    expected = "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7Face2efcde9"
    assert sha256_file(test_file) == expected


@pytest.mark.unit
def test_write_sha256_sidecar(tmp_path: Path):
    test_file = tmp_path / "data.txt"
    test_file.write_text("test data", encoding="utf-8")

    sidecar = write_sha256_sidecar(test_file)

    assert sidecar.exists()
    assert sidecar.name == "data.txt.sha256"
    
    expected_hash = sha256_file(test_file)
    assert sidecar.read_text(encoding="utf-8") == f"{expected_hash}  data.txt\n"


# ============================================================================
# 2. KeyBuilder Tests
# ============================================================================
@pytest.mark.unit
def test_key_builder_paths(storage_config: StorageConfig, storage_context: JobStorageContext):
    builder = ResultsKeyBuilder(storage_config, storage_context)

    expected_prefix = "ast-results/env=dev/date=2026-03-31/job_id=job-12345"
    assert builder.job_prefix == expected_prefix
    
    # Test stripping leading slashes
    assert builder.key("/logs/out.txt") == f"{expected_prefix}/logs/out.txt"
    assert builder.key("logs/out.txt") == f"{expected_prefix}/logs/out.txt"
    
    # Test canonical URI generation
    assert builder.uri("data/file.csv") == f"s3://test-bucket/{expected_prefix}/data/file.csv"


# ============================================================================
# 3. Local Writer Tests
# ============================================================================
@pytest.mark.unit
def test_local_writer_raises_without_local_root(storage_context: JobStorageContext):
    config = StorageConfig(bucket="b", environment="dev", local_root=None)
    with pytest.raises(ValueError, match="local_root is required"):
        LocalResultsStorageWriter(config, storage_context)


@pytest.mark.unit
def test_local_writer_put_file_and_text(
    storage_config: StorageConfig,
    storage_context: JobStorageContext,
    tmp_path: Path
):
    writer = LocalResultsStorageWriter(storage_config, storage_context)

    # Test put_text
    text_uri = writer.put_text("hello text", relative_key="notes/hello.txt")
    text_file_path = storage_config.local_root / writer.keys.key("notes/hello.txt")
    
    assert text_file_path.exists()
    assert text_file_path.read_text(encoding="utf-8") == "hello text"
    assert text_uri == text_file_path.as_uri()

    # Test put_file
    source_file = tmp_path / "source.bin"
    source_file.write_bytes(b"\x00\x01\x02\x03")

    file_uri = writer.put_file(source_file, relative_key="raw/binary.bin")
    dest_file_path = storage_config.local_root / writer.keys.key("raw/binary.bin")

    assert dest_file_path.exists()
    assert dest_file_path.read_bytes() == b"\x00\x01\x02\x03"
    assert file_uri == dest_file_path.as_uri()


# ============================================================================
# 4. Job Manifest Tests
# ============================================================================
@pytest.mark.unit
def test_job_manifest_to_dict_and_yaml():
    manifest = JobManifest(
        schema_version=1,
        job_id="job-123",
        created_at="2026-03-31T10:00:00Z",
        completed_at="2026-03-31T10:05:00Z",
        status="SUCCESS",
        engine_name="ast-engine",
        engine_version="1.0.0",
        artifacts={
            "raw_results": ArtifactRecord(
                key="results/results.raw.json",
                content_type="application/json",
                sha256="abc123hash",
                uri="s3://bucket/key"
            )
        }
    )

    d = manifest.to_dict()
    assert d["schema_version"] == 1
    assert d["job_id"] == "job-123"
    assert d["engine"]["name"] == "ast-engine"
    assert d["artifacts"]["raw_results"]["sha256"] == "abc123hash"

    yaml_out = manifest.to_yaml()
    assert "schema_version: 1" in yaml_out
    assert "job_id: job-123" in yaml_out
    assert "sha256: abc123hash" in yaml_out


# ============================================================================
# 5. Publisher Tests -- doesn't actually publish
# ============================================================================
@pytest.mark.unit
def test_publisher_publishes_required_and_optional_artifacts(tmp_path: Path):
    mock_writer = MagicMock()
    mock_writer.put_file.return_value = "s3://test-bucket/mocked-path"
    mock_writer.put_text.return_value = "s3://test-bucket/manifest.yaml"

    publisher = ResultsPublisher(writer=mock_writer)

    raw_results = tmp_path / "raw.json"
    raw_results.write_text("{}", encoding="utf-8")

    job_log = tmp_path / "job.log"
    job_log.write_text("info log", encoding="utf-8")

    manifest_uri = publisher.publish_job_results(
        job_id="job-123",
        created_at="2026-03-31T10:00:00Z",
        completed_at="2026-03-31T10:01:00Z",
        status="COMPLETED",
        engine_version="0.1.0",
        raw_results_json=raw_results,
        job_log=job_log,
    )

    assert manifest_uri == "s3://test-bucket/manifest.yaml"
    assert mock_writer.put_file.called
    assert mock_writer.put_text.called