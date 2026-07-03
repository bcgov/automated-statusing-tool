"""
Orchestrator demo - file-based, no database.

Builds an AOI from a local test shapefile, runs the three operators against
local test data through the orchestrator, and prints the assembled AstResults.
No BCGW connection is needed, so this is the quickest way to see the whole
pipeline (AOI -> adapter -> operator -> results) run end to end.

Run:
    uv run python scripts/orchestrator_run.py
"""

from pathlib import Path

import geopandas as gpd

from ast_engine.utils.logging_config import setup_logging
from ast_engine.core.aoi.aoi_builder import AOIBuilder, AOIRequest
from ast_engine.core.execution import AnalysisTask, run_analysis

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "ast_engine" / "tests" / "data"
SHP = DATA_DIR / "Test_Shape_A" / "Test_Shape_A_shp" / "Test_Shape_A.shp"  # the AOI box
POINTS = DATA_DIR / "Test_Overlay" / "points.shp"
POLYGONS = DATA_DIR / "Test_Overlay" / "polygons.shp"


def build_aoi():
    """Build an AreaOfInterest from the Test_Shape_A box (BC Albers / EPSG:3005)."""
    gdf = gpd.read_file(SHP)
    request = AOIRequest(aoi_id="demo_aoi", name="Demo AOI", target_crs="EPSG:3005")
    return AOIBuilder().from_gdf(request, gdf)


def demo_tasks() -> list[AnalysisTask]:
    """A hand-made task per operator, all reading local files.

    These stand in for what the registry -> task mapper produces at run time;
    the orchestrator does not care where the tasks came from.
    """
    return [
        AnalysisTask(
            dataset_id="1", dataset_name="Test polygons", source_type="file",
            datasource=str(POLYGONS), operator="overlay", geom_type="polygon",
            keep_properties=["Name"],
        ),
        AnalysisTask(
            dataset_id="2", dataset_name="Test points", source_type="file",
            datasource=str(POINTS), operator="within_distance", distance_m=500.0,
            keep_properties=["Name"],
        ),
        AnalysisTask(
            dataset_id="3", dataset_name="Test box (self)", source_type="file",
            datasource=str(SHP), operator="adjacency", tolerance_m=0.0,
        ),
    ]


def print_results(results) -> None:
    print(f"\n=== AstResults  job_id={results.job_id}  aoi_id={results.aoi_id} ===")
    for group in results.results:
        print(f"\nDataset: {group.dataset_name}  (id={group.dataset_id})")
        if not group.results:
            print("  (no result - analysis failed, see log above)")
            continue
        for result in group.results:
            print(
                f"  operator={result.operator_type.value}"
                f"  features={result.feature_count}"
                f"  measure={result.measure_value} {result.measure_unit}"
            )
            for feature in result.features[:5]:
                print(f"    - id={feature.feature_id}  measure={feature.measure}  props={feature.properties}")


def main() -> None:
    setup_logging()
    aoi = build_aoi()
    results = run_analysis(aoi=aoi, tasks=demo_tasks(), job_id="demo-job")
    print_results(results)


if __name__ == "__main__":
    main()
