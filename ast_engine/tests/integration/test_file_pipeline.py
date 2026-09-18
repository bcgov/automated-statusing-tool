"""
End-to-end tests over the sample datasets committed in tests/data/.

These run the real chain - AOI builder -> FileSpatialAdapter -> operator ->
run_analysis - with no database:

    uv run pytest -m integration

Tasks are built straight as AnalysisTask objects rather than read from a
registry yaml, so these tests check the run itself, not the registry format.
"""

from pathlib import Path

import geopandas as gpd
import pytest

from ast_engine.core.aoi.aoi_builder import AOIBuilder, AOIRequest
from ast_engine.core.execution import AnalysisTask, run_analysis
from ast_engine.core.results import (
    AdjacencyResult,
    AstResults,
    DatasetResultGroup,
    PolyOverlayResult,
    ProximityResult,
)


# --- Test data --------------------------------------------------------------
DATA_DIR = Path(__file__).parents[1] / "data"

# The AOI in KML, which is EPSG:4326 - the shapefile version comes from the
# `aoi` fixture in conftest.py.
AOI_KML = DATA_DIR / "Test_Shape_A" / "Test_Shape_A.kml"

# The parcel fabric, read from the file geodatabase. The datasource carries the
# layer name after the .gdb, the way the registry stores it.
PARCELS_GDB = (
    DATA_DIR
    / "Test_Data_PMBC_PARCEL_FABRIC.gdb"
    / "WHSE_CADASTRE_PMBC_PARCEL_FABRIC_POLY_FA_SVW"
)
ROADS_SHP = (
    DATA_DIR
    / "Test_Data_FOREST_TENURE_ROAD_shp"
    / "WHSE_FOREST_TENURE_FTEN_ROAD_SECTION_LINES_SVW.shp"
)

# What Test_Shape_A actually covers in this sample data.
PARCELS_IN_AOI = 10
PARCEL_OVERLAP_SQM = 3855513.945
PRIVATE_PARCELS_IN_AOI = 3        # of the 10, the ones with OWNER_TYPE 'Private'
ROADS_CROSSING_AOI = 6
ROADS_WITHIN_100M = 7             # the 6 crossing plus one 34 m away


# --- Helpers ----------------------------------------------------------------
def _file_task(name: str, datasource, operator: str, **params) -> AnalysisTask:
    """One file dataset to analyse, as the registry mapper would build it."""
    return AnalysisTask(
        dataset_id=name,
        dataset_name=name,
        source_type="file",
        datasource=str(datasource),
        operator=operator,
        **params,
    )


def _only_result(group: DatasetResultGroup):
    """Pull the single result out of one dataset's group.

    A dataset that failed to read comes back as an empty group, so check for
    that first and name it in the failure.
    """
    assert group.results, f"dataset {group.dataset_name!r} produced no result - the read failed"
    return group.results[0]


# --- The tests --------------------------------------------------------------
@pytest.mark.integration
def test_gdb_layer_reads(aoi):
    """A feature class inside a file geodatabase runs through the whole chain.

    The datasource names the layer after the .gdb, the way the registry stores
    it, so this also covers the adapter splitting that string into a path and a
    layer. Nothing else in the test suite opens a file geodatabase.
    """
    task = _file_task("parcels", PARCELS_GDB, "overlay", geom_type="polygon")

    results = run_analysis(aoi=aoi, tasks=[task], job_id="it-parcels")
    result = _only_result(results.results[0])

    assert isinstance(result, PolyOverlayResult)
    assert result.feature_count == PARCELS_IN_AOI
    assert result.total_area == pytest.approx(PARCEL_OVERLAP_SQM, rel=1e-6)


@pytest.mark.integration
def test_run_analysis_over_three_operators(aoi):
    """One run covering all three analyses sends each dataset to the right
    operator and returns the matching result type.

    The parcels task also carries the two things a registry dataset brings with
    it: an attribute filter (where) and report fields (keep_properties).
    """
    tasks = [
        _file_task(
            "parcels",
            PARCELS_GDB,
            "overlay",
            geom_type="polygon",
            keep_properties=["PID"],
            where={"conditions": [{"field": "OWNER_TYPE", "op": "=", "value": "Private"}]},
        ),
        _file_task("roads", ROADS_SHP, "within_distance", distance_m=100.0),
        _file_task("parcel_edges", PARCELS_GDB, "adjacency", tolerance_m=1.0),
    ]

    results = run_analysis(aoi=aoi, tasks=tasks, job_id="it-three-operators")

    assert isinstance(results, AstResults)
    assert len(results.results) == 3
    parcels, roads, edges = (_only_result(group) for group in results.results)

    # overlay on polygons -> PolyOverlayResult. The where filter cut the 10
    # parcels in the AOI down to the privately owned ones, and each result
    # record carries the PID that keep_properties asked for.
    assert isinstance(parcels, PolyOverlayResult)
    assert parcels.feature_count == PRIVATE_PARCELS_IN_AOI
    assert all("PID" in feature.properties for feature in parcels.features)

    # within_distance -> ProximityResult, picking up roads near the AOI as
    # well as the ones crossing it
    assert isinstance(roads, ProximityResult)
    assert roads.feature_count == ROADS_WITHIN_100M

    # adjacency -> AdjacencyResult; parcel edges run along the AOI boundary
    assert isinstance(edges, AdjacencyResult)
    assert edges.is_adjacent is True


@pytest.mark.integration
def test_failed_dataset_is_isolated(aoi):
    """A dataset that cannot be read comes back as an empty group while the
    rest of the run still produces results, and nothing is raised.
    """
    tasks = [
        _file_task("parcels", PARCELS_GDB, "overlay", geom_type="polygon"),
        _file_task("missing", DATA_DIR / "no_such_file.shp", "overlay", geom_type="polygon"),
        _file_task("roads", ROADS_SHP, "overlay", geom_type="line"),
    ]

    results = run_analysis(aoi=aoi, tasks=tasks, job_id="it-failed-dataset")

    # one group per dataset, still in task order
    assert [group.dataset_name for group in results.results] == ["parcels", "missing", "roads"]
    parcels, missing, roads = results.results

    assert missing.results == []
    assert _only_result(parcels).feature_count == PARCELS_IN_AOI
    assert _only_result(roads).feature_count == ROADS_CROSSING_AOI


@pytest.mark.integration
def test_kml_aoi_reprojects():
    """An AOI read from KML arrives in lat/long, and the AOI builder
    reprojects it to BC Albers - it then finds the same parcels as the
    shapefile AOI does.
    """
    kml_gdf = gpd.read_file(AOI_KML)
    assert kml_gdf.crs.to_epsg() == 4326

    request = AOIRequest(
        aoi_id="it_aoi_kml",
        name="Integration AOI from KML",
        target_crs="EPSG:3005",
    )
    kml_aoi = AOIBuilder().from_gdf(request, kml_gdf)
    assert kml_aoi.crs_epsg == 3005

    task = _file_task("parcels", PARCELS_GDB, "overlay", geom_type="polygon")
    results = run_analysis(aoi=kml_aoi, tasks=[task], job_id="it-kml-aoi")
    result = _only_result(results.results[0])

    assert result.feature_count == PARCELS_IN_AOI
    # Reprojecting from lat/long moves the AOI boundary by a fraction of a
    # millimetre, so the overlap area matches within a tolerance, not exactly.
    assert result.total_area == pytest.approx(PARCEL_OVERLAP_SQM, rel=1e-6)
