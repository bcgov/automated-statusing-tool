"""
Shared fixtures for the integration tests.

Two kinds of test live in tests/integration/:

- test_file_pipeline.py runs a whole analysis over the sample datasets already
  committed in tests/data/. It needs no database, so anyone can run it.
- test_bcgw.py runs real SDO queries against BCGW, so it needs a BCGW login.

BCGW credentials are read from the environment only - BCGW_USER, BCGW_PASSWORD
and BCGW_HOST. When the variables are not set the BCGW tests report
as skipped, naming what is missing, and the file tests still run.

How to run: the file tests run on Windows and Linux alike and need nothing
set up:

    uv run pytest -m integration

To include the BCGW tests, set the three variables in your own shell first.
See the engine README ("BCGW credentials for the integration tests") for the
exact commands on Windows and Linux.
"""

import os
from pathlib import Path

import geopandas as gpd
import pytest

from ast_engine.core.aoi.aoi_builder import AOIBuilder, AOIRequest, AreaOfInterest
from ast_engine.core.data_adapters.oracle import OracleAdapter, OracleConnection


@pytest.fixture(scope="session")
def data_dir() -> Path:
    """The tests/data folder holding the sample datasets."""
    return Path(__file__).parents[1] / "data"


@pytest.fixture(scope="session")
def aoi_gdf(data_dir) -> gpd.GeoDataFrame:
    """Test_Shape_A straight off disk, in BC Albers (EPSG:3005).

    This is the AOI in the form an adapter takes for its spatial filter.
    """
    shp = data_dir / "Test_Shape_A" / "Test_Shape_A_shp" / "Test_Shape_A.shp"
    return gpd.read_file(shp)


@pytest.fixture(scope="session")
def aoi(aoi_gdf) -> AreaOfInterest:
    """Test_Shape_A built into an AreaOfInterest - the form the operators take."""
    request = AOIRequest(
        aoi_id="it_aoi",
        name="Integration AOI",
        target_crs="EPSG:3005",
    )
    return AOIBuilder().from_gdf(request, aoi_gdf)


@pytest.fixture(scope="session")
def bcgw_credentials() -> tuple[str, str, str]:
    """The BCGW login read from the environment, or skip the test.

    The skip message names whichever variables are missing, so a tester
    without BCGW access can see why the test did not run.
    """
    names = ("BCGW_USER", "BCGW_PASSWORD", "BCGW_HOST")
    values = [os.environ.get(name) for name in names]

    missing = [name for name, value in zip(names, values) if not value]
    if missing:
        pytest.skip(f"BCGW credentials not set: {', '.join(missing)}")

    return values[0], values[1], values[2]


@pytest.fixture(scope="session")
def bcgw_connection(bcgw_credentials):
    """One open BCGW connection, reused by every test in the run.

    If the credentials are set but the login fails, the error is allowed
    through rather than skipped: setting the variables says you meant to reach
    BCGW, and skipping would hide a real outage.
    """
    user, password, host = bcgw_credentials
    connection = OracleConnection(user, password, host)
    try:
        yield connection
    finally:
        connection.close()


@pytest.fixture(scope="session")
def oracle_adapter(bcgw_connection) -> OracleAdapter:
    """An OracleAdapter reading through the shared BCGW connection."""
    return OracleAdapter(bcgw_connection.connection, bcgw_connection.cursor)
