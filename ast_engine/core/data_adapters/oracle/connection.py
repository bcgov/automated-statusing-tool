"""Oracle database connection management.

Provides a context manager around `oracledb.connect()` so the
application can open one connection per AST run and pass it down
to adapter calls. The OracleAdapter does NOT create connections
itself. This module is the single point where credentials enter.
"""

import logging
from typing import Any

import oracledb

logger = logging.getLogger(__name__)


class OracleConnection:
    """Context manager for an Oracle database session.

    Usage:
        with OracleConnection(user, pwd, host) as (conn, cur):
            adapter = OracleAdapter(connection=conn, cursor=cur)
            gdf = adapter.read(table=..., aoi=...)
    """

    def __init__(self, username: str, password: str, hostname: str):
        self.username = username
        self.password = password
        self.hostname = hostname
        self.connection: Any = None
        self.cursor: Any = None
        self._connect()

    def _connect(self) -> None:
        try:
            self.connection = oracledb.connect(
                user=self.username,
                password=self.password,
                dsn=self.hostname,
            )
            self.cursor = self.connection.cursor()
            logger.info("Connected to Oracle database at %s", self.hostname)
        except oracledb.DatabaseError as exc:
            raise ConnectionError(
                f"Oracle connection failed for {self.hostname}: {exc}"
            ) from exc

    def __enter__(self):
        return self.connection, self.cursor

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self) -> None:
        if self.cursor is not None:
            try:
                self.cursor.close()
            except Exception as exc:
                logger.warning("Error closing Oracle cursor: %s", exc)
            self.cursor = None

        if self.connection is not None:
            try:
                self.connection.close()
            except Exception as exc:
                logger.warning("Error closing Oracle connection: %s", exc)
            self.connection = None
