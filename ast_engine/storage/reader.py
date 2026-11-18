# ast/ast_engine/storage/reader.py

from abc import ABC, abstractmethod


class ResultsStorageReader(ABC):
    """Reads a job's published artifacts back out of results storage.

    The counterpart of ResultsStorageWriter: the worker writes a job's results
    with a writer, and whatever serves them afterwards (the API) reads them with
    a reader built from the same storage settings and the same job context, so
    both resolve a relative key to the same place.
    """

    @abstractmethod
    def get_bytes(self, relative_key: str) -> bytes:
        """
        Return the bytes stored under a key relative to the job's folder.

        Raises FileNotFoundError when nothing is stored under that key.
        """
        raise NotImplementedError

    def get_text(self, relative_key: str) -> str:
        """
        Return the text stored under a key relative to the job's folder.

        Raises FileNotFoundError when nothing is stored under that key.
        """
        return self.get_bytes(relative_key).decode("utf-8")
