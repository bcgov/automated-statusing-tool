"""
Live BCGW tests - these run real SDO queries against the warehouse.

They need a BCGW login in the environment (BCGW_USER, BCGW_PASSWORD,
BCGW_HOST). Without it every test here reports as skipped and the rest of the
integration suite still runs. See the engine README for how to set them.

    uv run pytest -m integration

What these cover that the unit tests cannot: the unit tests in
tests/unit/test_adapter_oracle.py replace the database with a fake object, so
they prove the adapter builds the right SQL but never prove that SQL runs.
These do.

Feature counts are mostly not asserted, because BCGW is live production data -
parcels get subdivided and districts get reorganised. What is asserted is that
each query runs, comes back in the expected CRS, and hands over geometry that
is usable.
"""

import geopandas as gpd
import pytest

from ast_engine.core.data_adapters.base import ReadOptions, SpatialFilter
from ast_engine.core.data_adapters.oracle import fetch_tantalis_aoi
from ast_engine.core.execution import AnalysisTask, run_analysis
from ast_engine.core.results import PolyOverlayResult


# --- BCGW tables--------------------------------------------
# PMBC is listed in PROBLEMATIC_TABLES (oracle/utils.py), so every read below
# also exercises the server-side curve fix that densifies arcs and repairs
# rings before the geometry is sent back as text.
PMBC = "WHSE_CADASTRE.PMBC_PARCEL_FABRIC_POLY_FA_SVW"
PMBC_ID = "PARCEL_FABRIC_POLY_ID"

DISTRICTS = "WHSE_ADMIN_BOUNDARIES.ADM_NR_DISTRICTS_SP"

GRID = "WHSE_BASEMAPPING.BCGS_20K_GRID"
GRID_FCODE = "RG90020000"

# A Crown tenure used for the test
TANTALIS_FILE_NUMBER = "1409125"
TANTALIS_DISPOSITION_ID = 163346
TANTALIS_PARCEL_ID = 820668


# --- The tests --------------------------------------------------------------
@pytest.mark.integration
@pytest.mark.parametrize(
    "predicate, filter_kwargs, must_find_features",
    [
        ("intersects", {}, True),
        ("within_distance", {"distance": 100.0}, True),
        ("touches", {}, False),
        ("nearest", {"k": 3}, True),
    ],
    ids=["intersects", "within_distance", "touches", "nearest"],
)
def test_predicate_reads(oracle_adapter, aoi_gdf, predicate, filter_kwargs, must_find_features):
    """Each of the four SDO query templates runs against BCGW and gives back
    geometry we can use.

    Geometry that is parseable, valid and non-empty is also the curve-fix
    check: when the server-side densify / rectify fails, parcel geometry comes
    back as something shapely cannot read or as an invalid shape.

    'touches' is allowed to find nothing - no parcel edge lines up exactly with
    the AOI boundary, which is a real answer rather than a failure.
    """
    options = ReadOptions(
        spatial_filter=SpatialFilter(aoi=aoi_gdf, predicate=predicate, **filter_kwargs),
        keep_columns=[PMBC_ID],
    )

    gdf = oracle_adapter.read(read_options=options, table=PMBC)

    assert isinstance(gdf, gpd.GeoDataFrame)
    assert gdf.crs.to_epsg() == 3005
    assert gdf.geometry.is_valid.all()
    assert not gdf.geometry.is_empty.any()

    if must_find_features:
        assert not gdf.empty
    if predicate == "nearest":
        # SDO_NN with sdo_num_res, capped again by ROWNUM in the template
        assert len(gdf) <= filter_kwargs["k"]


@pytest.mark.integration
def test_read_without_keep_columns(oracle_adapter, aoi_gdf):
    """A read that asks for no particular columns returns every attribute plus
    usable geometry.

    This is what happens when a registry dataset names no unique_id and no
    aggregate_columns, so the operator passes no column list. The geometry
    column must not come back as an attribute of its own - the query already
    returns it as WKT.
    """
    options = ReadOptions(
        spatial_filter=SpatialFilter(aoi=aoi_gdf, predicate="intersects")
    )

    gdf = oracle_adapter.read(read_options=options, table=PMBC)

    assert not gdf.empty
    assert gdf.crs.to_epsg() == 3005
    assert gdf.geometry.is_valid.all()
    # one geometry column, named by geopandas - no leftover SHAPE attribute
    assert "SHAPE" not in gdf.columns
    assert PMBC_ID in gdf.columns


@pytest.mark.integration
def test_where_and_keep_columns_push_down(oracle_adapter, aoi_gdf):
    """The attribute filter and the column list both reach the SDO query.

    The adapter clears them off the ReadOptions once they are in the SQL, so
    the base class does not filter a second time on top of a result that is
    already filtered.
    """
    options = ReadOptions(
        spatial_filter=SpatialFilter(aoi=aoi_gdf, predicate="intersects"),
        where={"conditions": [{"field": "FCODE", "op": "=", "value": GRID_FCODE}]},
        keep_columns=["FCODE", "MAP_TILE"],
    )

    gdf = oracle_adapter.read(read_options=options, table=GRID)

    assert not gdf.empty
    assert set(gdf.columns) == {"FCODE", "MAP_TILE", "geometry"}
    assert (gdf["FCODE"] == GRID_FCODE).all()
    assert options.where is None
    assert options.definition_query is None

    # A filter that matches nothing must come back empty. Without this, a
    # filter that never reached the query would still look like it worked.
    # A fresh ReadOptions is required - the adapter empties the one above.
    no_match = ReadOptions(
        spatial_filter=SpatialFilter(aoi=aoi_gdf, predicate="intersects"),
        where={"conditions": [{"field": "FCODE", "op": "=", "value": "NOT_A_REAL_FCODE"}]},
        keep_columns=["FCODE", "MAP_TILE"],
    )
    assert oracle_adapter.read(read_options=no_match, table=GRID).empty


@pytest.mark.integration
def test_describe_live(oracle_adapter):
    """describe() reads a BCGW table's details from Oracle's own dictionary.

    One call covers the geometry column, SRID, geometry type, column list and
    row count lookups.
    """
    info = oracle_adapter.describe(table=DISTRICTS)

    assert info.crs == "EPSG:3005"
    assert info.geometry_type == "polygon"
    assert info.geom_column
    assert info.columns
    assert info.row_count > 0


@pytest.mark.integration
def test_fetch_tantalis_aoi(bcgw_connection):
    """A known Crown tenure parcel resolves to AOI geometry we can use.

    This is the AOI source for Tantalis-driven runs, as opposed to a user
    supplying their own shapefile.
    """
    gdf = fetch_tantalis_aoi(
        bcgw_connection.connection,
        bcgw_connection.cursor,
        TANTALIS_FILE_NUMBER,
        TANTALIS_DISPOSITION_ID,
        TANTALIS_PARCEL_ID,
    )

    assert not gdf.empty
    assert gdf.crs.to_epsg() == 3005
    assert gdf.geometry.is_valid.all()
    assert not gdf.geometry.is_empty.any()
    # Tantalis parcels can be multipart. The lookup hands back the raw BCGW
    # geometry - splitting it into parts is the AOI module's job, not this one.
    assert gdf.geom_type.isin(["Polygon", "MultiPolygon"]).all()


@pytest.mark.integration
def test_run_analysis_over_bcgw(aoi, data_dir, bcgw_connection):
    """A run mixing a BCGW dataset and a local file, on a connection the caller
    opened.

    This is the one test that proves the engine works with a connection it did
    not open itself - it never asks for credentials and never prompts.

    Both tasks read the same parcel fabric: one live from BCGW, one from the
    extract committed in tests/data/. They cover the same AOI, so they should
    report the same overlap. If this fails on the numbers rather than on an
    error, the saved extract has drifted from what is now in BCGW.
    """
    parcels_gdb = (
        data_dir
        / "Test_Data_PMBC_PARCEL_FABRIC.gdb"
        / "WHSE_CADASTRE_PMBC_PARCEL_FABRIC_POLY_FA_SVW"
    )
    tasks = [
        AnalysisTask(
            dataset_id="1",
            dataset_name="parcels_bcgw",
            source_type="oracle",
            datasource=PMBC,
            operator="overlay",
            geom_type="polygon",
            feature_id_field=PMBC_ID,
        ),
        AnalysisTask(
            dataset_id="2",
            dataset_name="parcels_file",
            source_type="file",
            datasource=str(parcels_gdb),
            operator="overlay",
            geom_type="polygon",
            feature_id_field=PMBC_ID,
        ),
    ]

    results = run_analysis(
        aoi=aoi,
        tasks=tasks,
        job_id="it-bcgw",
        oracle_connection=bcgw_connection,
    )

    assert len(results.results) == 2
    bcgw_group, file_group = results.results
    assert bcgw_group.results, "the BCGW dataset produced no result - the read failed"
    assert file_group.results, "the file dataset produced no result - the read failed"

    from_bcgw = bcgw_group.results[0]
    from_file = file_group.results[0]

    assert isinstance(from_bcgw, PolyOverlayResult)
    assert from_bcgw.feature_count > 0
    assert from_bcgw.feature_count == from_file.feature_count
    assert from_bcgw.total_area == pytest.approx(from_file.total_area, rel=1e-6)
