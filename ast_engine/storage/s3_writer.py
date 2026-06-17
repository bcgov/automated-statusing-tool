# ast/ast_engine/storage/s3_writer.py

from pathlib import Path
from typing import Mapping, Optional

import boto3

from .key_builder import ResultsKeyBuilder
from .models import StorageConfig, JobStorageContext
from .writer import ResultsStorageWriter


class S3ResultsStorageWriter(ResultsStorageWriter):
    def __init__(self, config: StorageConfig, context: JobStorageContext):
        self.config = config
        self.context = context
        self.keys = ResultsKeyBuilder(config, context)

        self.client = boto3.client(
            "s3",
            endpoint_url=config.endpoint_url,
            region_name=config.region_name,
        )

    def put_file(
        self,
        local_path: Path,
        relative_key: str,
        content_type: Optional[str] = None,
        metadata: Optional[Mapping[str, str]] = None,
    ) -> str:
        object_key = self.keys.key(relative_key)

        extra_args = {}

        if content_type:
            extra_args["ContentType"] = content_type

        if metadata:
            extra_args["Metadata"] = dict(metadata)

        self.client.upload_file(
            Filename=str(local_path),
            Bucket=self.config.bucket,
            Key=object_key,
            ExtraArgs=extra_args or None,
        )

        return f"s3://{self.config.bucket}/{object_key}"

    def put_text(
        self,
        text: str,
        relative_key: str,
        content_type: str = "text/plain",
        metadata: Optional[Mapping[str, str]] = None,
    ) -> str:
        object_key = self.keys.key(relative_key)

        put_args = {
            "Bucket": self.config.bucket,
            "Key": object_key,
            "Body": text.encode("utf-8"),
            "ContentType": content_type,
        }

        if metadata:
            put_args["Metadata"] = dict(metadata)

        self.client.put_object(**put_args)

        return f"s3://{self.config.bucket}/{object_key}"