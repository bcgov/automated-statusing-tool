# ast/ast_engine/storage/s3_reader.py

import boto3
from botocore.exceptions import ClientError

from .key_builder import ResultsKeyBuilder
from .models import StorageConfig, JobStorageContext
from .reader import ResultsStorageReader

# S3 error codes that mean "there is no such object".
_NOT_FOUND_CODES = {"NoSuchKey", "404"}


class S3ResultsStorageReader(ResultsStorageReader):
    def __init__(self, config: StorageConfig, context: JobStorageContext):
        self.config = config
        self.context = context
        self.keys = ResultsKeyBuilder(config, context)

        self.client = boto3.client(
            "s3",
            aws_access_key_id=config.access_id,
            aws_secret_access_key=config.access_key.get_secret_value(),
            endpoint_url=config.endpoint_url,
            use_ssl=config.use_ssl,
        )

    def get_text(self, relative_key: str) -> str:
        object_key = self.keys.key(relative_key)

        try:
            response = self.client.get_object(
                Bucket=self.config.bucket,
                Key=object_key,
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in _NOT_FOUND_CODES:
                raise FileNotFoundError(
                    f"s3://{self.config.bucket}/{object_key}"
                ) from exc
            raise

        return response["Body"].read().decode("utf-8")
