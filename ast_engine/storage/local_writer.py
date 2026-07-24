# ast_engine/storage/local_writer.py

'''
local_writer.py contains the same classes and methods as s3_writer for use in developement and tests
'''

# ast/ast_engine/storage/local_writer.py

import shutil
from pathlib import Path
from typing import Mapping, Optional

from .key_builder import ResultsKeyBuilder
from .models import StorageConfig, JobStorageContext
from .writer import ResultsStorageWriter


class LocalResultsStorageWriter(ResultsStorageWriter):
    def __init__(self, config: StorageConfig, context: JobStorageContext):
        if not config.local_root:
            raise ValueError("local_root is required for LocalResultsStorageWriter")

        self.config = config
        self.context = context
        self.keys = ResultsKeyBuilder(config, context)

    def put_file(
        self,
        local_path: Path,
        relative_key: str,
        content_type: Optional[str] = None,
        metadata: Optional[Mapping[str, str]] = None,
    ) -> str:
        destination = self.config.local_root / self.keys.key(relative_key)
        destination.parent.mkdir(parents=True, exist_ok=True)

        shutil.copy2(local_path, destination)

        return destination.as_uri()

    def put_text(
        self,
        text: str,
        relative_key: str,
        content_type: str = "text/plain",
        metadata: Optional[Mapping[str, str]] = None,
    ) -> str:
        destination = self.config.local_root / self.keys.key(relative_key)
        destination.parent.mkdir(parents=True, exist_ok=True)

        destination.write_text(text, encoding="utf-8")

        return destination.as_uri()