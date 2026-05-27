"""
oracle_smoke.py - query BCGW with the real OracleAdapter

A stanadlone script for sanity-checking the Oracle adapter against a live
BCGW connection. NOT a pytest test - this runs manually.

Why this script
----------------------
The unit tests in tests/unit/test_oracle_adapter.py use a MagicMock (fake object) cursor,
to prove the adapter logic but CANNOT test that the SDO SQL actually
runs against BCGW. This script closes that gap, also tests
the server-side curve fix by using PMBC dataset.

What it does
------------
1. Prompts for BCGW credentials. The password is read with getpass so it
   does not echo to the terminal. Nothing is written!
2. Opens an Oracle connection.
3. Reads Test_Shape_A from the test data as AOI.
4. Runs four reads against PMBC_PARCEL_FABRIC_POLY_FA_SVW, one per predicate:
   intersects, within_distance (100 m), touches, nearest (k=3).
5. Prints row count + a small preview of each result.

Success = each read returns a GeoDataFrame with parseable geometry.

How to run
----------
    uv run python scripts/oracle_smoke.py

"""
from __future__ import annotations

import getpass
import sys
from pathlib import Path

import geopandas as gpd

from ast_engine.core.data_adapters.base import ReadOptions, SpatialFilter
from ast_engine.core.data_adapters.oracle import OracleAdapter, OracleConnection


TABLE = "WHSE_CADASTRE.PMBC_PARCEL_FABRIC_POLY_FA_SVW"

REPO_ROOT = Path(__file__).resolve().parents[1]
TEST_AOI_SHP = (
    REPO_ROOT
    / "ast_engine"
    / "tests"
    / "data"
    / "Test_Shape_A"
    / "Test_Shape_A_shp"
    / "Test_Shape_A.shp"
)


def _get_credentials() -> tuple[str, str, str]:
    """Prompt for BCGW credentials.
    Password is read with getpass so it never echoes to the terminal.
    """
    user = input("BCGW username: ").strip()
    password = getpass.getpass("BCGW password: ")
    host = input("BCGW host/DSN (e.g. bcgw.bcgov:1521/idwprod1.bcgov): ").strip()
    if not (user and password and host):
        sys.exit("Missing credentials; aborting.")
    return user, password, host


def _load_aoi() -> gpd.GeoDataFrame:
    """Use the Test_Shape_A test polygon as the AOI."""
    if not TEST_AOI_SHP.exists():
        sys.exit(f"Test AOI not found at {TEST_AOI_SHP}")
    aoi = gpd.read_file(TEST_AOI_SHP)
    print(f"AOI: {len(aoi)} feature(s) in {aoi.crs}")
    return aoi


def _run_one(adapter: OracleAdapter, aoi: gpd.GeoDataFrame, predicate: str,
             *, distance: float | None = None, k: int | None = None) -> None:
    """Run one predicate against PMBC and print a small summary."""
    label = predicate + (f" (distance={distance} m)" if distance else "")
    label = label + (f" (k={k})" if k else "")
    print(f"\n--- {label} ---")

    opts = ReadOptions(
        spatial_filter=SpatialFilter(
            aoi=aoi, predicate=predicate, distance=distance, k=k
        ),
        # small column list so the terminal printout is readable.
        keep_columns=["PARCEL_FABRIC_POLY_ID", "PIN", "PID", "OWNER_TYPE"],
    )

    try:
        gdf = adapter.read(read_options=opts, table=TABLE)
    except Exception as exc:
        print(f"  FAILED: {type(exc).__name__}: {exc}")
        return

    print(f"  rows: {len(gdf)}, crs: {gdf.crs}")
    if not gdf.empty:
        # Show the columns we asked for plus any adapter-added metadata
        # (RESULT, DISTANCE_M). geometry left out of the printout - too long.
        cols = [c for c in gdf.columns if c != gdf.geometry.name]
        print(gdf[cols].head(3).to_string(index=False))

        # Geometry sanity check: at least one parsed shapely object. to make sure the curve fix worked
        first_geom = gdf.geometry.iloc[0]
        print(f"  first geometry: {first_geom.geom_type}, "
              f"valid={first_geom.is_valid}, empty={first_geom.is_empty}")


def main() -> None:
    user, password, host = _get_credentials()
    aoi = _load_aoi()

    print(f"\nConnecting to {host} as {user} ...")
    with OracleConnection(user, password, host) as (conn, cur):
        adapter = OracleAdapter(connection=conn, cursor=cur)
        print(f"Querying {TABLE} (curve fix is applied automatically; "
              f"see PROBLEMATIC_TABLES in oracle/utils.py)")

        _run_one(adapter, aoi, "intersects")
        _run_one(adapter, aoi, "within_distance", distance=100.0)
        _run_one(adapter, aoi, "touches")
        _run_one(adapter, aoi, "nearest", k=3)

    print("\nDone.")


if __name__ == "__main__":
    main()
