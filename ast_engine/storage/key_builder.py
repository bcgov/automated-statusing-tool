# ast/ast_engine/storage/key_builder.py

from .models import StorageConfig, JobStorageContext


class ResultsKeyBuilder:
    def __init__(self, config: StorageConfig, context: JobStorageContext):
        self.config = config
        self.context = context

    @property
    def job_prefix(self) -> str:
        return (
            f"{self.config.prefix}/"
            f"env={self.config.environment}/"
            f"date={self.context.created_date}/"
            f"job_id={self.context.job_id}"
        )

    def key(self, relative_path: str) -> str:
        relative_path = relative_path.lstrip("/")
        return f"{self.job_prefix}/{relative_path}"

    def uri(self, relative_path: str) -> str:
        return f"s3://{self.config.bucket}/{self.key(relative_path)}"