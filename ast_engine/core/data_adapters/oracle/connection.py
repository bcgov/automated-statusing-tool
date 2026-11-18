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
            options = ReadOptions(spatial_filter=SpatialFilter(aoi=aoi_gdf))
            gdf = adapter.read(read_options=options, table="WHSE...")
    """

    def __init__(
        self,
        username: str,
        password: str,
        hostname: str,
        client_lib_dir: str | None = None,
    ):
        """
        client_lib_dir: folder holding Oracle's own client libraries (Instant
            Client). Left out, the driver talks to the database by itself,
            which needs nothing installed. Some accounts cannot sign in that
            way: one whose password is stored in an older form is refused with
            DPY-3015, and connects once this is given.
        """
        # Password is intentionally NOT stored on self - it is only needed
        # during _connect() and keeping it as an instance attribute would
        # extend its lifetime unnecessarily (and trip CodeQL's taint analysis
        # on every later self.* access).
        self.username = username
        self.hostname = hostname
        self.connection: Any = None
        self.cursor: Any = None
        if client_lib_dir:
            self._use_oracle_client(client_lib_dir)
        self._connect(password)

    def _use_oracle_client(self, client_lib_dir: str) -> None:
        """Have the driver connect through Oracle's client libraries.

        This is a switch for the whole process and can be thrown once, so it is
        left alone when an earlier connection has already thrown it.
        """
        if not oracledb.is_thin_mode():
            return
        try:
            oracledb.init_oracle_client(lib_dir=client_lib_dir)
        except oracledb.Error as exc:
            raise ConnectionError(
                f"Oracle client libraries could not be loaded from {client_lib_dir}: {exc}"
            ) from exc
        logger.info("Using the Oracle client libraries in %s", client_lib_dir)

    def _connect(self, password: str) -> None:
        try:
            self.connection = oracledb.connect(
                user=self.username,
                password=password,
                dsn=self.hostname,
            )
            self.cursor = self.connection.cursor()
            logger.info("Connected to Oracle database")
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
