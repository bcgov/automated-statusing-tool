#\tests\unit\test_oracle_adapter.py
"""
OracleAdapter unit tests (mock-test, no live Oracle connection)

- Test the adapter logic without a real Oracle conneciton.
- A MagicMock (fake object) stands in for the connection and cursor.
- monkeypatch replaces the helper functions that would otherwise call Oracle
  (geometry column, SRID, columns lookups).
- The mock cursor returns an empty result set, so the adapter exits cleanly
  after the SQL string and bind variables have been captured.

This test does NOT prove the SDO-SQL works against BCGW. 
For that see we need BCGW coredentials and a real table. 
That is tested in this seeprate script (not a pytest test) that we run manually:
  scripts/oracle_smoke.py

"""
from unittest.mock import MagicMock

import pytest
import geopandas as gpd
from shapely.geometry import Polygon

from ast_engine.core.data_adapters.oracle.adapter import OracleAdapter
from ast_engine.core.data_adapters.oracle import utils
from ast_engine.core.data_adapters.oracle.utils import _gtype_to_geometry_type
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
# This tests the logic for clearing definition_query, which would otherwise
# be re-applied in pandas (.query) by the base class post-filter on top of
# the SDO push-down.
# keep_columns is not cleared - the SQL SELECT already returns the
# requested columns, so the base class's slice keeps the same set the SQL
# returned (redundent). spatial_filter is also not cleared - the base post-filter does
# not read it.
# ---------------------------------------------------------------------------

def test_oracle_adapter_clears_definition_query(_mock_adapter, _aoi):
    """After the read, definition_query must be None so the base class
    post-filter does not re-apply it on top of the SDO WHERE clause."""
    adapter, _ = _mock_adapter
    opts = ReadOptions(
        spatial_filter=SpatialFilter(aoi=_aoi, predicate="intersects"),
        definition_query="STATUS = 'ACTIVE'",
        keep_columns=["OBJECTID"],
    )
    adapter._read_impl(read_options=opts, table=TABLE)

    assert opts.definition_query is None


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


# ---------------------------------------------------------------------------
# describe() - build-time metadata
# (the metadata helpers are patched, so no Oracle is touched; we check that
# describe() assembles them into a DatasetInfo.)
# ---------------------------------------------------------------------------

def test_oracle_adapter_describe(monkeypatch):
    """describe() assembles DatasetInfo from the metadata helpers."""
    monkeypatch.setattr(utils, "get_geometry_column", lambda *a, **k: "SHAPE")
    monkeypatch.setattr(utils, "get_srid", lambda *a, **k: 3005)
    monkeypatch.setattr(utils, "get_geometry_type", lambda *a, **k: "polygon")
    monkeypatch.setattr(utils, "get_columns", lambda *a, **k: ["OBJECTID", "SHAPE"])
    monkeypatch.setattr(utils, "get_row_count", lambda *a, **k: 42)

    adapter = OracleAdapter(connection=MagicMock(), cursor=MagicMock())
    info = adapter.describe(table=TABLE)

    assert info.geom_column == "SHAPE"
    assert info.crs == "EPSG:3005"
    assert info.geometry_type == "polygon"
    assert info.columns == ["OBJECTID", "SHAPE"]
    assert info.row_count == 42


# ---------------------------------------------------------------------------
# SDO_GTYPE -> point/line/polygon mapping (pure, no Oracle)
# SDO_GTYPE is DLTT; the last two digits are the type. Multipart (5/6/7)
# collapses to its single-part name; 4 (collection) is not handled.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "gtype, expected",
    [
        (2001, "point"),
        (2002, "line"),
        (2003, "polygon"),
        (2005, "point"),    # multipoint
        (2006, "line"),     # multiline
        (2007, "polygon"),  # multipolygon
        (3003, "polygon"),  # 3D polygon
        (2004, None),       # collection - unsupported
    ],
)
def test_gtype_to_geometry_type(gtype, expected):
    assert _gtype_to_geometry_type(gtype) == expected
