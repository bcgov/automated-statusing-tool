# ast/ast_engine/storage/writer.py

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Mapping, Optional


class ResultsStorageWriter(ABC):
    @abstractmethod
    def put_file(
        self,
        local_path: Path,
        relative_key: str,
        content_type: Optional[str] = None,
        metadata: Optional[Mapping[str, str]] = None,
    ) -> str:
        """
        Store a local file and return its canonical URI.
        """
        raise NotImplementedError

    @abstractmethod
    def put_text(
        self,
        text: str,
        relative_key: str,
        content_type: str = "text/plain",
        metadata: Optional[Mapping[str, str]] = None,
    ) -> str:
        """
        Store generated text content and return its canonical URI.
        """
        raise NotImplementedError