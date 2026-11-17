# ast/ast_engine/storage/local_reader.py

'''
local_reader.py reads what local_writer.py wrote, for use in development and tests
'''

from .key_builder import ResultsKeyBuilder
from .models import StorageConfig, JobStorageContext
from .reader import ResultsStorageReader


class LocalResultsStorageReader(ResultsStorageReader):
    def __init__(self, config: StorageConfig, context: JobStorageContext):
        if not config.local_root:
            raise ValueError("local_root is required for LocalResultsStorageReader")

        self.config = config
        self.context = context
        self.keys = ResultsKeyBuilder(config, context)

    def get_bytes(self, relative_key: str) -> bytes:
        source = self.config.local_root / self.keys.key(relative_key)

        # Path.read_bytes already raises FileNotFoundError for a missing file.
        return source.read_bytes()
