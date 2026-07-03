"""
Orchestrator smoke run - live BCGW + timing.

Runs the orchestrator against one or more real registry YAMLs (provincial /
regional / Tab 1), for one AOI, over a live BCGW connection. Prints how long the
run took and which datasets were slowest - the numbers we need to think about
efficiency (where parallelism would help, which datasets dominate a run).

Registry YAMLs are kept OUTSIDE the repo (some dataset paths may be sensitive),
so point --registry at the generated YAMLs in the workspace.

Credentials come from BCGW_USER / BCGW_PASSWORD / BCGW_HOST if set, else you are
prompted (the password is read with getpass, never echoed). BCGW_PWD is also
accepted as an alias for the password (this script only). File datasets need no
connection; the connection is only opened if a registry has Oracle datasets.

Examples:
    # one provincial registry against the default test AOI
    uv run python scripts/orchestrator_smoke.py \\
        --registry "//.../workspace/.../provincial_common.yaml"

    # provincial + west-coast + Tab 1, against a real AOI file
    uv run python scripts/orchestrator_smoke.py \\
        --registry prov.yaml --registry west_coast.yaml --registry tab1_registry.yaml \\
        --aoi "//.../my_aoi.shp"
"""

import argparse
import os
import time
from collections import Counter
from pathlib import Path

import geopandas as gpd
import pandas as pd

from ast_engine.utils.logging_config import setup_logging
from ast_engine.utils.diagnostics import DiagnosticTracker
from ast_engine.config.registry import utils as registry_utils
from ast_engine.core.aoi.aoi_builder import AOIBuilder, AOIRequest
from ast_engine.core.execution import run_analysis, tasks_from_registries

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AOI = REPO_ROOT / "ast_engine" / "tests" / "data" / "Test_Shape_A" / "Test_Shape_A_shp" / "Test_Shape_A.shp"


def _bridge_password_alias() -> None:
    """Local convenience for this script only: accept BCGW_PWD as an alias for
    BCGW_PASSWORD.

    The repo code (execution.py) reads BCGW_PASSWORD; this copies BCGW_PWD into it
    for this process so either name works when you run the smoke. Only affects this
    script's own environment - nothing in the package is changed.
    """
    if not os.environ.get("BCGW_PASSWORD") and os.environ.get("BCGW_PWD"):
        os.environ["BCGW_PASSWORD"] = os.environ["BCGW_PWD"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the orchestrator against real registry YAMLs over BCGW.")
    parser.add_argument(
        "--registry", action="append", required=True, metavar="YAML",
        help="Path to a registry YAML. Repeat to combine several (provincial + regional + Tab 1).",
    )
    parser.add_argument(
        "--aoi", default=str(DEFAULT_AOI), metavar="FILE",
        help="AOI file (shapefile / KML / GeoJSON ...). Defaults to the Test_Shape_A box.",
    )
    parser.add_argument("--job-id", default="smoke-job", help="Job id recorded on the results.")
    parser.add_argument(
        "--out", default="orchestrator_results.xlsx", metavar="XLSX",
        help="Where to write the results spreadsheet (summary + features sheets).",
    )
    return parser.parse_args()


def build_aoi(aoi_path: str):
    """Build an AreaOfInterest from a file, reprojected to BC Albers (EPSG:3005)."""
    gdf = gpd.read_file(aoi_path)
    request = AOIRequest(aoi_id="smoke_aoi", name="Smoke AOI", target_crs="EPSG:3005")
    return AOIBuilder().from_gdf(request, gdf)


def load_registries(paths: list[str]):
    """Load each YAML into (name, Registry); the name (file stem) tags provenance."""
    registries = []
    for path in paths:
        registry = registry_utils.load_yaml(Path(path))
        registries.append((Path(path).stem, registry))
        print(f"Loaded {len(registry.datasets)} datasets from {path}")
    return registries


def print_timing_summary(tracker: DiagnosticTracker, wall_seconds: float) -> None:
    """Summarise per-dataset timings captured by the tracker."""
    done = [s for s in tracker.snapshots if s.step in ("dataset_done", "dataset_failed")]
    by_operator = Counter(s.extra.get("operator") for s in done)
    by_source = Counter(s.extra.get("source") for s in done)
    failed = [s for s in done if s.step == "dataset_failed"]
    timed = sorted(done, key=lambda s: s.extra.get("seconds", 0.0), reverse=True)

    print("\n================ RUN SUMMARY ================")
    print(f"Datasets run : {len(done)}  (failed: {len(failed)})")
    print(f"By operator  : {dict(by_operator)}")
    print(f"By source    : {dict(by_source)}")
    print(f"Wall time    : {wall_seconds:.1f} s")
    if done:
        print(f"Avg / dataset: {sum(s.extra.get('seconds', 0.0) for s in done) / len(done):.2f} s")
    print("\nSlowest datasets:")
    for snap in timed[:10]:
        print(f"  {snap.extra.get('seconds', 0.0):7.2f} s  {snap.extra.get('operator'):<16} {snap.step.split('_')[-1]:<7} {snap.extra.get('dataset')}")
    print("=============================================")


def write_results_spreadsheet(tasks, results, tracker: DiagnosticTracker, out_path: Path) -> None:
    """Write the run to an .xlsx with two sheets.

    summary  - one row per analysis: which registry it came from, dataset,
               operator, status, feature count, the headline measure (+ its unit),
               and how long it took.
    features - one row per matched feature: its id, its own measure (distance /
               overlap / shared border), and the report fields (aggregate_columns)
               as text.

    tasks, results.results and the per-dataset timing snapshots are all produced
    in the same order (one per analysis), so they line up by position.
    """
    dataset_snaps = [s for s in tracker.snapshots if s.step in ("dataset_done", "dataset_failed")]

    summary_rows = []
    feature_rows = []
    for i, (task, group) in enumerate(zip(tasks, results.results)):
        snap = dataset_snaps[i] if i < len(dataset_snaps) else None
        seconds = snap.extra.get("seconds") if snap else None
        failed = bool(snap and snap.step == "dataset_failed")
        result = group.results[0] if group.results else None

        summary_rows.append({
            "registry": task.source_registry,
            "dataset": task.dataset_name,
            "datasource": task.datasource,
            "source": task.source_type,
            "operator": task.operator,
            "status": "failed" if failed else "ok",
            "features": result.feature_count if result else 0,
            "measure_value": result.measure_value if result else None,
            "measure_unit": result.measure_unit if result else None,
            "seconds": seconds,
        })

        if result:
            for feature in result.features:
                feature_rows.append({
                    "registry": task.source_registry,
                    "dataset": task.dataset_name,
                    "operator": result.operator_type.value,
                    "feature_id": feature.feature_id,
                    "measure": feature.measure,
                    "properties": "; ".join(f"{k}={v}" for k, v in feature.properties.items()),
                })

    out_path.parent.mkdir(parents=True, exist_ok=True)
    feature_cols = ["registry", "dataset", "operator", "feature_id", "measure", "properties"]
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        pd.DataFrame(summary_rows).to_excel(writer, sheet_name="summary", index=False)
        # features can be empty (nothing intersected the AOI); still write the sheet
        feat_df = pd.DataFrame(feature_rows) if feature_rows else pd.DataFrame(columns=feature_cols)
        feat_df.to_excel(writer, sheet_name="features", index=False)


def main() -> None:
    args = parse_args()
    setup_logging()
    _bridge_password_alias()

    registries = load_registries(args.registry)
    tasks = tasks_from_registries(registries)
    print(f"Total analyses to run: {len(tasks)}")

    aoi = build_aoi(args.aoi)
    tracker = DiagnosticTracker()

    start = time.perf_counter()
    results = run_analysis(aoi=aoi, tasks=tasks, job_id=args.job_id, tracker=tracker)
    wall = time.perf_counter() - start

    print_timing_summary(tracker, wall)
    print(f"\nAssembled AstResults: {len(results.results)} dataset groups, job_id={results.job_id}")

    out_path = Path(args.out)
    write_results_spreadsheet(tasks, results, tracker, out_path)
    print(f"Results spreadsheet written to {out_path.resolve()}")


if __name__ == "__main__":
    main()
