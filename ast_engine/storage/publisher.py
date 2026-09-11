# ast/ast_engine/storage/publisher.py

from pathlib import Path
from typing import Dict, Optional,List

from .checksums import sha256_file, write_sha256_sidecar
from .manifest import ArtifactRecord, JobManifest
from .models import OperatorArtifact
from .writer import ResultsStorageWriter

# TODO: Refine ResultsPublisher to match results
class ResultsPublisher:
    def __init__(self, writer: ResultsStorageWriter):
        self.writer = writer

    def publish_job_results(
        self,
        *,
        job_id: str,
        user: str,
        created_at: str,
        completed_at: str,
        execution_time: str,
        status: str,
        engine_version: str,
        raw_results_json: Path,
        summary_results_json: Optional[Path] = None,
        validation_report_json: Optional[Path] = None,
        operator_outputs: Optional[List[OperatorArtifact]] = None,
        extracted_pmtiles: Optional[Path] = None,
        request_parameters_yaml: Optional[Path] = None,
        aoi_geojson: Optional[Path] = None,
        aoi_gpkg: Optional[Path] = None,
        config_yaml: Optional[Path] = None,
        source_datasets_yaml: Optional[Path] = None,
        job_log: Optional[Path] = None,
        spatial_metadata: Optional[Dict] = None,
        inputs_metadata: Optional[Dict] = None,
    ) -> str:
        artifacts: Dict[str, ArtifactRecord] = {}

        def upload_artifact(
            name: str,
            path: Path,
            relative_key: str,
            content_type: str,
            checksum: bool = True,
            extra_metadata: Optional[Dict[str, str]] = None,
        ) -> None:
            digest = sha256_file(path) if checksum else None
            meta = {
                "job_id": job_id,
                "artifact_name": name,
            }
            if extra_metadata:
                meta.update(extra_metadata)

            uri = self.writer.put_file(
                path,
                relative_key,
                content_type=content_type,
                metadata=meta,
            )

            artifacts[name] = ArtifactRecord(
                key=relative_key,
                content_type=content_type,
                sha256=digest,
                uri=uri,
                metadata=extra_metadata
            )

            if checksum:
                sidecar = write_sha256_sidecar(path)
                self.writer.put_file(
                    sidecar,
                    f"{relative_key}.sha256",
                    content_type="text/plain",
                    metadata={
                        "job_id": job_id,
                        "artifact_name": f"{name}_sha256",
                    },
                )

        upload_artifact(
            "raw_results",
            raw_results_json,
            "results/results.raw.json",
            "application/json",
        )

        if summary_results_json:
            upload_artifact(
                "summary_results",
                summary_results_json,
                "results/results.summary.json",
                "application/json",
            )

        if validation_report_json:
            upload_artifact(
                "validation_report",
                validation_report_json,
                "results/validation-report.json",
                "application/json",
            )

        if operator_outputs:
            for item in operator_outputs:
                artifact_name = f"gpkg_{item.registry}_{item.operator}_{item.dataset_name}"
                relative_key = f"data/{item.registry}/{item.operator}/{item.dataset_name}.gpkg"

                item_metadata = {
                    "registry": item.registry,
                    "operator": item.operator,
                    "dataset_name": item.dataset_name,
                }

                upload_artifact(
                    name=artifact_name,
                    path=item.path,
                    relative_key=relative_key,
                    content_type="application/geopackage+sqlite3",
                    checksum=True,
                    extra_metadata=item_metadata,
                )

        if extracted_pmtiles:
            upload_artifact(
                "pmtiles",
                extracted_pmtiles,
                "data/pmtiles/extracted.pmtiles",
                "application/vnd.pmtiles",
            )

        if request_parameters_yaml:
            upload_artifact(
                "request_parameters",
                request_parameters_yaml,
                "request/request-parameters.yaml",
                "application/yaml",
                checksum=False,
            )

        if aoi_geojson:
            upload_artifact(
                "aoi_geojson",
                aoi_geojson,
                "request/area-of-interest/aoi.geojson",
                "application/geo+json",
            )

        if aoi_gpkg:
            upload_artifact(
                "aoi_geopackage",
                aoi_gpkg,
                "request/area-of-interest/aoi.gpkg",
                "application/geopackage+sqlite3",
            )

        if config_yaml:
            upload_artifact(
                "config",
                config_yaml,
                "provenance/config.yaml",
                "application/yaml",
                checksum=False,
            )

        if source_datasets_yaml:
            upload_artifact(
                "source_datasets",
                source_datasets_yaml,
                "provenance/source-datasets.yaml",
                "application/yaml",
                checksum=False,
            )

        if job_log:
            upload_artifact(
                "job_log",
                job_log,
                "logs/job.log",
                "text/plain",
                checksum=False,
            )

        manifest = JobManifest(
            schema_version=1,
            job_id=job_id,
            user=user,
            created_at=created_at,
            completed_at=completed_at,
            execution_time=execution_time,
            status=status,
            engine_name="ast-engine",
            engine_version=engine_version,
            artifacts=artifacts,
            spatial=spatial_metadata,
            inputs=inputs_metadata,
        )

        return self.writer.put_text(
            manifest.to_yaml(),
            "manifest.yaml",
            content_type="application/yaml",
            metadata={
                "job_id": job_id,
                "artifact_name": "manifest",
            },
        )