"""
Tantalis status lookups (mock tests, no live Oracle connection).

A MagicMock stands in for the cursor: each test sets the rows a query returns
and checks what the lookup makes of them and what it sent to Oracle.

These tests do NOT prove the SQL runs against BCGW - the table and column names
are the ones the ArcGIS Pro tool queries, and only a run against the live
warehouse can confirm them.
"""

from datetime import datetime
from unittest.mock import MagicMock

import geopandas as gpd
import oracledb
import pytest
from shapely.geometry import box

from ast_engine.core.data_adapters.exceptions import DataReadError
from ast_engine.core.data_adapters.oracle import tantalis_status
from ast_engine.core.data_adapters.oracle.tantalis_status import (
    InactiveTenure,
    fetch_applicant_name,
    fetch_inactive_tenures,
    fetch_received_dates,
    fetch_tenure_details,
)

pytestmark = pytest.mark.unit


def _cursor(rows: list[tuple]) -> MagicMock:
    cursor = MagicMock()
    cursor.fetchall.return_value = rows
    return cursor


def _inactive_row(disposition_id, file_number, organization=None, individual=" ", parcel_id=1,
                  purpose="QUARRYING", tenure_type="LICENCE") -> tuple:
    """One row of the inactive-tenure query, in its column order."""
    return (
        parcel_id, disposition_id, file_number, "TENURE", "INACT", "EXPIRED", datetime(2020, 1, 1),
        purpose, "SAND AND GRAVEL", tenure_type, "LICENCE OF OCCUPATION", "Somewhere", organization, individual,
    )


# --- Tenure details ----------------------------------------------------------
def test_tenure_details_returns_each_field_as_text():
    cursor = _cursor([(12.5, "LICENCE", 987654.0, "LICENCE OF OCCUPATION", "QUARRYING", "SAND AND GRAVEL",
                       "Tin Cup Lake", "DISTRICT LOT 1")])

    details = fetch_tenure_details(cursor, "7410123", "55", "987654")

    assert details["TENURE_AREA_IN_HECTARES"] == ["12.5"]
    assert details["TENURE_TYPE"] == ["LICENCE"]
    # A whole number is shown without ".0".
    assert details["INTRID_SID"] == ["987654"]
    assert details["TENURE_LEGAL_DESCRIPTION"] == ["DISTRICT LOT 1"]


def test_tenure_details_binds_the_three_identifiers():
    cursor = _cursor([])

    fetch_tenure_details(cursor, "7410123", "55", "987654")

    sql, bind_vars = cursor.execute.call_args.args
    assert bind_vars == {"file_nbr": "7410123", "disp_id": "55", "parcel_id": "987654"}
    # The identifiers go to Oracle as bind variables, never into the SQL text.
    assert "7410123" not in sql


def test_tenure_details_are_empty_when_no_parcel_matches():
    details = fetch_tenure_details(_cursor([]), "1", "2", "3")

    assert set(details) == set(tantalis_status.TENURE_FIELDS)
    assert all(values == [] for values in details.values())


def test_tenure_details_leave_out_a_missing_value():
    cursor = _cursor([(None, "LICENCE", 1, None, None, None, None, None)])

    details = fetch_tenure_details(cursor, "1", "2", "3")

    assert details["TENURE_AREA_IN_HECTARES"] == []
    assert details["TENURE_TYPE"] == ["LICENCE"]


# --- Applicant and received date ---------------------------------------------
@pytest.mark.parametrize(
    "rows, expected",
    [
        ([("ACME GRAVEL LTD.", None, None)], "ACME GRAVEL LTD."),
        ([(None, "Alex", "Smith")], "Alex Smith"),
        ([("ACME GRAVEL LTD.", None, None), (None, "Alex", "Smith")], "ACME GRAVEL LTD.; Alex Smith"),
        ([("ACME GRAVEL LTD.", None, None), ("ACME GRAVEL LTD.", None, None)], "ACME GRAVEL LTD."),
        ([], ""),
    ],
)
def test_applicant_name(rows, expected):
    assert fetch_applicant_name(_cursor(rows), "55") == expected


def test_received_dates_are_returned_as_text():
    cursor = _cursor([(datetime(2026, 3, 31),)])

    assert fetch_received_dates(cursor, "55") == ["2026-03-31 00:00:00"]
    assert cursor.execute.call_args.args[1] == {"disp_id": "55"}


def test_a_database_error_is_reported_as_a_read_error():
    cursor = MagicMock()
    cursor.execute.side_effect = oracledb.DatabaseError("ORA-00942: table or view does not exist")

    with pytest.raises(DataReadError, match="Tantalis applicant lookup failed"):
        fetch_applicant_name(cursor, "55")


# --- Inactive tenures --------------------------------------------------------
@pytest.fixture
def aoi() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(geometry=[box(0, 0, 100, 100)], crs="EPSG:3005")


def _with_parcels(monkeypatch, parcel_ids: list) -> MagicMock:
    """Have the interest-parcel read return these parcel ids, and return the
    stand-in adapter so a test can see what it was asked for."""
    adapter = MagicMock()
    adapter.read.return_value = gpd.GeoDataFrame(
        {"INTRID_SID": parcel_ids},
        geometry=[box(0, 0, 1, 1)] * len(parcel_ids),
        crs="EPSG:3005",
    )
    monkeypatch.setattr(tantalis_status, "OracleAdapter", MagicMock(return_value=adapter))
    return adapter


def test_inactive_tenures_are_read_for_the_parcels_the_aoi_touches(monkeypatch, aoi):
    adapter = _with_parcels(monkeypatch, [22.0, 11.0, 22.0])
    cursor = _cursor([_inactive_row(900, "7410123", organization="ACME GRAVEL LTD.")])

    tenures = fetch_inactive_tenures(MagicMock(), cursor, aoi)

    assert tenures == [
        InactiveTenure(disposition_id=900, file_number="7410123", interest_type="QUARRYING LICENCE",
                       holders="ACME GRAVEL LTD."),
    ]
    # The parcels are found by shape, on the interest parcel shapes table...
    read = adapter.read.call_args.kwargs
    assert read["table"] == "WHSE_TANTALIS.TA_INTEREST_PARCEL_SHAPES"
    assert read["read_options"].spatial_filter.predicate == "intersects"
    # ...and the tenures are then read for those parcel ids, each once.
    assert "IP.INTRID_SID IN (11,22)" in cursor.execute.call_args.args[0]


def test_no_parcels_means_no_tenures_and_no_tenure_query(monkeypatch, aoi):
    _with_parcels(monkeypatch, [])
    cursor = _cursor([])

    assert fetch_inactive_tenures(MagicMock(), cursor, aoi) == []
    cursor.execute.assert_not_called()


def test_a_tenure_with_several_holders_is_listed_once(monkeypatch, aoi):
    """The query returns a row per holder and per parcel of a tenure."""
    _with_parcels(monkeypatch, [1, 2])
    cursor = _cursor([
        _inactive_row(900, "7410123", organization="ACME GRAVEL LTD.", parcel_id=1),
        _inactive_row(900, "7410123", organization="ACME GRAVEL LTD.", parcel_id=2),
        _inactive_row(900, "7410123", individual="Alex Smith", parcel_id=1),
        _inactive_row(800, "7400001", individual="Sam Lee", purpose="AGRICULTURE", tenure_type="LEASE"),
    ])

    tenures = fetch_inactive_tenures(MagicMock(), cursor, aoi)

    assert [(tenure.disposition_id, tenure.holders) for tenure in tenures] == [
        (900, "ACME GRAVEL LTD. / Alex Smith"),
        (800, "Sam Lee"),
    ]
    assert tenures[1].interest_type == "AGRICULTURE LEASE"


def test_a_long_parcel_list_is_split_into_lists_oracle_accepts():
    condition = tantalis_status._parcel_condition(range(1, 2502))

    assert condition.count("IP.INTRID_SID IN (") == 3
    assert condition.count(" OR ") == 2
    assert condition.startswith("(") and condition.endswith(")")


def test_a_parcel_id_that_is_not_a_number_is_never_written_into_sql():
    with pytest.raises(ValueError):
        tantalis_status._parcel_condition(["1) OR 1=1 --"])
