#\tests\unit\test_oracle_adapter.py
"""
OracleAdapter unit tests (mock-test, no live Oracle connection)

- Test the adapter logic without a real Oracle conneciton.
- A MagicMock (fake object) stands in for the connection and cursor.
- monkeypatch replaces the helper functions that would otherwise call Oracle
  (geometry column, SRID, columns lookups).
- The mock cursor returns an empty result set, so the adapter exits cleanly
  after the SQL string and bind variables have been captured.

This tesst does NOT prove the SDO SQL works against BCGW. For that see:
  scripts/oracle_smoke.py

"""
from unittest.mock import MagicMock

import pytest
import geopandas as gpd
from shapely.geometry import Polygon

from ast_engine.core.data_adapters.oracle.adapter import OracleAdapter
from ast_engine.core.data_adapters.oracle import utils
from ast_engine.core.data_adapters.base import ReadOptions, SpatialFilter
from ast_engine.core.data_adapters.exceptions import DataReadError


TABLE = "WHSE_TEST.FAKE_TABLE"

# Tags every test in this file as "unit"
# replaces a per-function @pytest.mark.unit decorator on each test
pytestmark = pytest.mark.unit


@pytest.fixture
def _aoi() -> gpd.GeoDataFrame:
    """A tiny AOI in EPSG:3005.

    Same SRID as the table SRID our mock returns (see _mock_adapter), so
    the adapter does NOT take the coordinate-transform branch.
    """
    return gpd.GeoDataFrame(
        geometry=[Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])],
        crs="EPSG:3005",
    )


@pytest.fixture
def _mock_adapter(monkeypatch):
    """Build an OracleAdapter wired to a fake cursor for one test.

    What the mock is faking:
      - cursor.description -> two columns: OBJECTID, SHAPE
      - cursor.fetchall()  -> [] (empty result set; the adapter takes
                              its "no features found" branch and returns
                              an empty GeoDataFrame, no geometry parsing)

    What monkeypatch patches for the test:
      - utils.get_geometry_column -> always returns "SHAPE"
      - utils.get_srid            -> always returns 3005
      - utils.get_columns         -> always returns ["OBJECTID", "SHAPE"]

    Returns (adapter, cursor) so tests can inspect what the cursor was
    called with after driving the adapter.
    """
    connection = MagicMock(name="connection")
    cursor = MagicMock(name="cursor")
    cursor.description = [("OBJECTID",), ("SHAPE",)]
    cursor.fetchall.return_value = []

    monkeypatch.setattr(utils, "get_geometry_column", lambda *a, **k: "SHAPE")
    monkeypatch.setattr(utils, "get_srid", lambda *a, **k: 3005)
    monkeypatch.setattr(utils, "get_columns", lambda *a, **k: ["OBJECTID", "SHAPE"])

    return OracleAdapter(connection=connection, cursor=cursor), cursor


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_oracle_adapter_raises_when_no_spatial_filter(_mock_adapter):
    """Without a SpatialFilter in ReadOptions, the adapter has no AOI to
    push down and should refuse to run."""
    adapter, _ = _mock_adapter
    with pytest.raises(DataReadError):
        adapter._read_impl(read_options=ReadOptions(), table=TABLE)


# ---------------------------------------------------------------------------
# This tests the logic for clearing the ReadOptions fields already pushed down by the oracle adapter 
# (definition_query, keep_columns, spatial_filter) 
# otherwise the base class _apply_post_filters will apply them a second time: 
# Query results are already filtered by the adapter, so the base class should not re-apply those filters.
# ---------------------------------------------------------------------------

def test_oracle_adapter_consumes_and_clears_read_options(_mock_adapter, _aoi):
    """After the read, every ReadOptions field the adapter used must be
    None so the base class post-filter does not re-apply it."""
    adapter, _ = _mock_adapter
    opts = ReadOptions(
        spatial_filter=SpatialFilter(aoi=_aoi, predicate="intersects"),
        definition_query="STATUS = 'ACTIVE'",
        keep_columns=["OBJECTID"],
    )
    adapter._read_impl(read_options=opts, table=TABLE)

    assert opts.spatial_filter is None
    assert opts.definition_query is None
    assert opts.keep_columns is None


# ---------------------------------------------------------------------------
# This test the SQL template selection
# pytest parametrize runs the same test function once per row in the list below.
# Each row supplies: (predicate, distance, k, SDO function we expect to see
# in the SQL string).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "predicate, distance, k, expected_sql_fragment",
    [
        ("intersects",      None,  None, "SDO_RELATE"),
        ("within_distance", 100.0, None, "SDO_WITHIN_DISTANCE"),
        ("touches",         None,  None, "SDO_RELATE"),
        ("nearest",         None,  1,    "SDO_NN"),
    ],
)
def test_oracle_adapter_picks_right_sql_template(
    _mock_adapter, _aoi, predicate, distance, k, expected_sql_fragment
):
    """For each predicate, the SQL passed to cursor.execute() must use the
    matching SDO function. We don't run the SQL - we just inspect it."""
    adapter, cursor = _mock_adapter
    opts = ReadOptions(
        spatial_filter=SpatialFilter(
            aoi=_aoi, predicate=predicate, distance=distance, k=k
        )
    )
    adapter._read_impl(read_options=opts, table=TABLE)

    # cursor.execute was called with (sql_string, bind_vars_dict). call_args
    # records that call - .args[0] is the SQL, .args[1] is the bind-vars dict.
    sql = cursor.execute.call_args.args[0]
    assert expected_sql_fragment in sql


def test_oracle_adapter_passes_k_for_nearest(_mock_adapter, _aoi):
    """The nearest predicate must put k into the bind-variables dict so the
    Oracle SDO_NN call knows how many features to return."""
    adapter, cursor = _mock_adapter
    opts = ReadOptions(
        spatial_filter=SpatialFilter(aoi=_aoi, predicate="nearest", k=5)
    )
    adapter._read_impl(read_options=opts, table=TABLE)

    bind_vars = cursor.execute.call_args.args[1]
    assert bind_vars.get("k") == 5
