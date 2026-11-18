"""
Tests for OracleConnection: how it reaches the database, with the Oracle driver
replaced so that no database is needed.
"""

from unittest.mock import MagicMock

import oracledb
import pytest

from ast_engine.core.data_adapters.oracle.connection import OracleConnection

pytestmark = pytest.mark.unit


@pytest.fixture
def driver(monkeypatch) -> MagicMock:
    """The Oracle driver's connect and client start-up, recorded not run."""
    calls = MagicMock()
    calls.thin = True

    def init_oracle_client(lib_dir=None):
        calls.init_oracle_client(lib_dir=lib_dir)
        calls.thin = False

    monkeypatch.setattr(oracledb, "connect", calls.connect)
    monkeypatch.setattr(oracledb, "init_oracle_client", init_oracle_client)
    monkeypatch.setattr(oracledb, "is_thin_mode", lambda: calls.thin)
    return calls


def test_a_connection_needs_no_oracle_client_by_default(driver):
    OracleConnection("user", "secret", "host:1521/db")

    driver.init_oracle_client.assert_not_called()
    driver.connect.assert_called_once_with(user="user", password="secret", dsn="host:1521/db")


def test_a_connection_uses_the_oracle_client_when_given_its_folder(driver):
    """Some accounts can only sign in through Oracle's own client libraries."""
    OracleConnection("user", "secret", "host:1521/db", client_lib_dir="/opt/oracle/instantclient")

    driver.init_oracle_client.assert_called_once_with(lib_dir="/opt/oracle/instantclient")
    driver.connect.assert_called_once()


def test_the_oracle_client_is_started_once_for_the_process(driver):
    """The driver refuses a second start; every job opens a new connection."""
    OracleConnection("user", "secret", "host:1521/db", client_lib_dir="/opt/oracle/instantclient")
    OracleConnection("user", "secret", "host:1521/db", client_lib_dir="/opt/oracle/instantclient")

    driver.init_oracle_client.assert_called_once()
    assert driver.connect.call_count == 2


def test_a_client_that_cannot_be_loaded_is_a_connection_error(driver, monkeypatch):
    def broken(lib_dir=None):
        raise oracledb.DatabaseError("DPI-1047: Cannot locate a 64-bit Oracle Client library")

    monkeypatch.setattr(oracledb, "init_oracle_client", broken)

    with pytest.raises(ConnectionError, match="Oracle client"):
        OracleConnection("user", "secret", "host:1521/db", client_lib_dir="/nowhere")
    driver.connect.assert_not_called()
