"""
Orchestrator smoke run - live BCGW + timing.

Runs the orchestrator against one or more real registry YAMLs (Tab 1 /
provincial / regional), for one AOI, over a live BCGW connection. Prints how
long the run took, which datasets were slowest, and how much of the time went to
Oracle versus local files - the numbers we need to talk about efficiency (where
parallelism would help, which datasets dominate a run).

Registry YAMLs are kept OUTSIDE the repo, so point --registry at the YAMLs you generated yourself with
ast_engine/config/spreadsheet_ingestion.py.

The AOI is either a file you point at with --aoi, or a Crown tenure parcel looked
up in Tantalis with --tenure-file / --disposition-id / --parcel-id. The Tantalis
lookup is the same one a real statusing run uses, so it is the closer match to
how the tool is actually driven.

Credentials come from the BCGW_USER / BCGW_PASSWORD / BCGW_HOST environment
variables. The connection is
opened only when it is needed - when a registry has Oracle datasets, or when the
AOI comes from Tantalis.

Saving the spatial output is optional and off by default. Pass --spatial-out
to turn it on; run the same registries twice, with and without, to see what the
spatial export costs. The per-dataset write times are reported separately, so a
single run with --spatial-out already tells you the write cost on its own.

Examples:
    # Tab 1 only, against the default test AOI (the committed Tab 1 yaml was
    # built on Linux, so it needs --ignore-os-check on Windows)
    uv run python scripts/orchestrator_smoke.py \\
        --registry ast_engine/config/registry/tab1/tab1.yaml --ignore-os-check

    # Tab 1 + provincial + one region, real AOI, with the spatial export on
    uv run python scripts/orchestrator_smoke.py \\
        --registry tab1.yaml --registry provincial.yaml --registry west_coast.yaml \\
        --aoi my_aoi.shp --spatial-out D:/ast_runs/west_coast --ignore-os-check

    # same, but the AOI is a Crown tenure parcel read from Tantalis
    uv run python scripts/orchestrator_smoke.py \\
        --registry tab1.yaml --registry provincial.yaml --registry west_coast.yaml \\
        --tenure-file 1409125 --disposition-id 163346 --parcel-id 820668 \\
        --spatial-out D:/ast_runs/west_coast --ignore-os-check
"""

import argparse
import os
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import geopandas as gpd
import pandas as pd
import yaml

from ast_engine.config.logging_config import setup_logging
from ast_engine.config.settings import Settings
from ast_engine.config.registry import utils as registry_utils
from ast_engine.core.aoi.aoi_builder import AOIBuilder, AOIRequest
from ast_engine.core.data_adapters.base import BaseSpatialAdapter
from ast_engine.core.data_adapters.oracle import OracleAdapter, OracleConnection, fetch_tantalis_aoi
from ast_engine.core.execution import build_tasks, run_analysis
# The orchestrator's own file-name cleaner, so the duplicate-output check below
# matches exactly what actually gets written to disk.
from ast_engine.core.execution import _safe_filename
from ast_engine.utils.diagnostics import DiagnosticTracker

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AOI = REPO_ROOT / "ast_engine" / "tests" / "data" / "Test_Shape_A" / "Test_Shape_A_shp" / "Test_Shape_A.shp"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the orchestrator against real registry YAMLs over BCGW.")
    parser.add_argument(
        "--registry", action="append", required=True, metavar="YAML",
        help="Path to a registry YAML. Repeat to combine several (Tab 1 + provincial + regional).",
    )
    parser.add_argument(
        "--aoi", default=None, metavar="FILE",
        help="AOI file (shapefile / KML / GeoJSON ...). Defaults to the Test_Shape_A box "
             "when no Tantalis parcel is given.",
    )
    # The other way to give an AOI: a Crown tenure parcel read straight from
    # Tantalis. All three identify one parcel and must be given together.
    parser.add_argument("--tenure-file", default=None, metavar="FILE_NBR",
                        help="Tantalis Crown lands file number, e.g. 1409125.")
    parser.add_argument("--disposition-id", default=None, metavar="DISP_ID",
                        help="Tantalis DISPOSITION_TRANSACTION_SID, e.g. 163346.")
    parser.add_argument("--parcel-id", default=None, metavar="PARCEL_ID",
                        help="Tantalis INTRID_SID, e.g. 820668.")
    parser.add_argument("--job-id", default="smoke-job", help="Job id recorded on the results.")
    parser.add_argument(
        "--out", default="orchestrator_results.xlsx", metavar="XLSX",
        help="Where to write the results spreadsheet (summary + features sheets).",
    )
    parser.add_argument(
        "--spatial-out", default=None, metavar="FOLDER",
        help="Save each dataset's matched features as a GeoPackage under this folder. "
             "Off by default. Keep it outside the repo.",
    )
    parser.add_argument(
        "--jsonl", default=None, metavar="FILE",
        help="Also write every diagnostic event to this JSONL file.",
    )
    parser.add_argument(
        "--ignore-os-check", action="store_true",
        help="Load a registry that was built on a different operating system. A YAML records "
             "which OS built it because its file paths are written in that OS's style; ignoring "
             "the check is safe for a registry of BCGW tables only (no paths), such as the "
             "committed Tab 1 yaml, and unsafe for a regional registry full of file paths.",
    )
    args = parser.parse_args()

    # The three Tantalis values identify one parcel, so they only make sense
    # together. Catch a half-filled set here rather than after the registries
    # have been loaded and a BCGW connection opened.
    tantalis = (args.tenure_file, args.disposition_id, args.parcel_id)
    if any(tantalis) and not all(tantalis):
        parser.error("--tenure-file, --disposition-id and --parcel-id must be given together.")
    if all(tantalis) and args.aoi:
        parser.error("Give either --aoi or the three Tantalis values, not both.")
    return args


# --- Read time vs operator time ---------------------------------------------
# The orchestrator times each dataset as one number covering both the adapter
# read and the operator's own geometry work. To see the split, this script wraps
# the adapter read for the length of the run and records how long each one took.
# It is done here rather than in the engine because it is a measurement, not
# something the engine has to carry into production.
#
# Reads are grouped by adapter type, not matched up to individual datasets, so
# nothing depends on the order they happen in.

READ_TIMES: dict[str, list[float]] = defaultdict(list)


def time_adapter_reads() -> None:
    """Record how long every adapter read takes, split by Oracle vs file."""
    original = BaseSpatialAdapter.read

    def read(self, **kwargs):
        start = time.perf_counter()
        try:
            return original(self, **kwargs)
        finally:
            source = "oracle" if isinstance(self, OracleAdapter) else "file"
            READ_TIMES[source].append(time.perf_counter() - start)

    BaseSpatialAdapter.read = read


def print_read_split(source_time: dict[str, float], spatial_on: bool) -> None:
    """Show how much of each source's time went on reading the data.

    Whatever is left after the read is the operator's own work - the geometry
    maths. If the read is nearly all of it, the run is waiting on the database
    and the network, which is the case parallel workers help most.
    """
    if not READ_TIMES:
        return
    print("\nRead vs operator time:")
    for source in sorted(READ_TIMES):
        reads = READ_TIMES[source]
        read_total = sum(reads)
        dataset_total = source_time.get(source, 0.0)
        rest = dataset_total - read_total
        share = (read_total / dataset_total * 100) if dataset_total else 0.0
        print(f"  {source:<8} {len(reads):>4} reads   read {read_total:>7.1f}s ({share:>4.1f}%)   "
              f"rest {rest:>6.1f}s   median read {statistics.median(reads):.2f}s")
    if spatial_on:
        print("  (\"rest\" also includes saving the GeoPackage - run without "
              "--spatial-out for a clean split)")


def uses_tantalis_aoi(args) -> bool:
    """True when the AOI is to be read from Tantalis rather than from a file."""
    return bool(args.tenure_file)


def build_aoi(args, connection):
    """Build the AreaOfInterest, reprojected to BC Albers (EPSG:3005).

    Two sources: a file on disk, or a Crown tenure parcel read from Tantalis by
    its file number / disposition / parcel triple - the same lookup a real
    statusing run uses. A Tantalis parcel can be multipart; splitting it into
    parts is the AOI module's job, so the raw geometry is handed straight to the
    builder.
    """
    if uses_tantalis_aoi(args):
        print(f"Reading AOI from Tantalis: file {args.tenure_file}, "
              f"disposition {args.disposition_id}, parcel {args.parcel_id}")
        gdf = fetch_tantalis_aoi(
            connection.connection,
            connection.cursor,
            args.tenure_file,
            args.disposition_id,
            args.parcel_id,
        )
        aoi_id = f"tantalis_{args.tenure_file}_{args.disposition_id}_{args.parcel_id}"
        name = f"Crown tenure {args.tenure_file}"
    else:
        aoi_path = args.aoi or str(DEFAULT_AOI)
        print(f"Reading AOI from file: {aoi_path}")
        gdf = gpd.read_file(aoi_path)
        aoi_id = "smoke_aoi"
        name = "Smoke AOI"

    request = AOIRequest(aoi_id=aoi_id, name=name, target_crs="EPSG:3005")
    aoi = AOIBuilder().from_gdf(request, gdf)
    print(f"AOI built: {aoi.footprint_area_ha:.1f} ha, {len(aoi.parts)} part(s), EPSG:{aoi.crs_epsg}")
    return aoi


def load_registries(paths: list[str], ignore_os_check: bool):
    """Load each YAML into a (name, Registry) pair; the file stem tags provenance.

    This is a stand-in for the run-time loader (load_registries(region)) that the
    engine still needs. Once the shape here holds over a couple of real regions,
    lift it into the engine as product code.
    """
    registries = []
    for path in paths:
        os_name = _registry_os(path) if ignore_os_check else None
        registry = registry_utils.load_yaml(Path(path), os_name=os_name)
        registries.append((Path(path).stem, registry))
        print(f"Loaded {len(registry.datasets)} datasets from {path}")
    return registries


def _registry_os(path: str) -> str | None:
    """Read the os stamp a registry YAML was built with.

    Handing this straight back to load_yaml is what makes --ignore-os-check work:
    the check then compares the stamp against itself and always passes.
    """
    with open(path, "r") as f:
        data = yaml.safe_load(f)
    return data.get("os")


def get_oracle_connection(tasks, needed_for_aoi: bool = False):
    """Open one BCGW connection for the run, or None when nothing needs Oracle.

    Two things can need it: a registry with Oracle datasets, and an AOI read from
    Tantalis. A file-only run with a file AOI needs no credentials at all.

    The engine never opens a connection itself, so the caller owns it. Credentials
    come from the environment only - there is no prompt, so this can be left
    running unattended.
    """
    if not needed_for_aoi and not any(task.source_type == "oracle" for task in tasks):
        print("No Oracle datasets and a file AOI - skipping the BCGW connection.")
        return None

    # Local convenience for this script only: accept BCGW_PWD as an alias.
    password = os.environ.get("BCGW_PASSWORD") or os.environ.get("BCGW_PWD")
    user = os.environ.get("BCGW_USER")
    host = os.environ.get("BCGW_HOST")
    missing = [
        name for name, value in
        (("BCGW_USER", user), ("BCGW_PASSWORD", password), ("BCGW_HOST", host))
        if not value
    ]
    if missing:
        sys.exit(
            f"This run needs BCGW but these environment variables are not set: "
            f"{', '.join(missing)}. Set them in your shell and run again."
        )
    print(f"Connecting to BCGW as {user}...")
    return OracleConnection(user, password, host)


def warn_about_duplicate_outputs(tasks) -> None:
    """Warn when two datasets in the SAME registry would be saved to one GeoPackage.

    The spatial output goes to <folder>/<registry>/<operator>/<dataset name>.gpkg,
    so two registries carrying the same dataset name each keep their own file.
    What is still not separated is the same name twice inside one registry -
    usually a duplicated row in the source spreadsheet. The second write replaces
    the first, and both results end up pointing at whatever survived.
    """
    by_path = defaultdict(list)
    for task in tasks:
        key = (task.source_registry, task.operator, _safe_filename(task.dataset_name))
        by_path[key].append(task)

    clashes = {path: group for path, group in by_path.items() if len(group) > 1}
    if not clashes:
        return
    print("\n*** WARNING: datasets that would share one spatial output file ***")
    for (registry, operator, filename), group in clashes.items():
        print(f"  {registry}/{operator}/{filename}.gpkg  <- {len(group)} datasets:")
        for task in group:
            print(f"      {task.dataset_name}   (datasource: {task.datasource})")
    print("Only the last one written will survive - most likely a duplicated "
          "row in that registry's spreadsheet.\n")


def percentile(values: list[float], fraction: float) -> float:
    """Simple percentile: the value below which that fraction of the run falls."""
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(int(round(fraction * (len(ordered) - 1))), len(ordered) - 1)
    return ordered[index]


def print_run_summary(tasks, results, tracker: DiagnosticTracker, wall_seconds: float,
                      spatial_on: bool = False) -> None:
    """Summarise the run: what ran, what found nothing, what failed, and timings.

    "Found nothing" and "failed" are different answers and are kept apart here.
    A dataset that ran and found no overlap is a real result; a dataset that
    failed is an error that needs looking at. Both come back with no features, so
    the status on each group is what separates them.
    """
    dataset_snaps = [s for s in tracker.snapshots if s.step in ("dataset_done", "dataset_failed")]

    ok_with_features = []
    ok_no_overlap = []
    failed = []
    # tasks, results.results and the per-dataset snapshots are all produced once
    # per analysis in the same order, so they line up by position. Position, not
    # dataset name - two registries can carry the same dataset name.
    for i, (task, group) in enumerate(zip(tasks, results.results)):
        snap = dataset_snaps[i] if i < len(dataset_snaps) else None
        seconds = snap.extra.get("seconds", 0.0) if snap else 0.0
        row = (task, group, seconds)
        if group.status == "failure":
            failed.append(row)
        elif group.results and group.results[0].feature_count > 0:
            ok_with_features.append(row)
        else:
            ok_no_overlap.append(row)

    all_rows = ok_with_features + ok_no_overlap + failed
    times = [seconds for _, _, seconds in all_rows]

    print("\n================ RUN SUMMARY ================")
    print(f"Datasets run     : {len(all_rows)}")
    print(f"  found features : {len(ok_with_features)}")
    print(f"  no overlap     : {len(ok_no_overlap)}")
    print(f"  failed         : {len(failed)}")
    print(f"Wall time        : {wall_seconds:.1f} s")
    if times:
        print(f"Per dataset      : median {statistics.median(times):.2f} s | "
              f"p95 {percentile(times, 0.95):.2f} s | max {max(times):.2f} s")

    # Oracle vs file: the direct input to the parallelization question.
    by_source_count = Counter(task.source_type for task, _, _ in all_rows)
    by_source_time = defaultdict(float)
    for task, _, seconds in all_rows:
        by_source_time[task.source_type] += seconds
    print("\nBy source:")
    for source in sorted(by_source_count):
        print(f"  {source:<8} {by_source_count[source]:>4} datasets   {by_source_time[source]:>8.1f} s")

    print_read_split(by_source_time, spatial_on)

    by_operator = Counter(task.operator for task, _, _ in all_rows)
    print(f"\nBy operator      : {dict(by_operator)}")

    print("\nSlowest 10 datasets:")
    for task, group, seconds in sorted(all_rows, key=lambda row: row[2], reverse=True)[:10]:
        features = group.results[0].feature_count if group.results else 0
        print(f"  {seconds:7.2f} s  {task.source_type:<7} {task.operator:<16} "
              f"{features:>6} feat  {task.dataset_name}")

    if failed:
        print(f"\nFailed datasets ({len(failed)}):")
        for task, group, seconds in failed:
            print(f"  {task.dataset_name}  ({task.source_registry}, {task.source_type})")
            print(f"      {group.error}")

    # What the spatial export cost, separated from the analysis itself.
    writes = [s for s in tracker.snapshots if s.step == "spatial_written"]
    if writes:
        write_seconds = sum(s.extra.get("seconds", 0.0) for s in writes)
        written_mb = sum(
            Path(s.extra["path"]).stat().st_size for s in writes if Path(s.extra["path"]).exists()
        ) / (1024 * 1024)
        print(f"\nSpatial export   : {len(writes)} files, {write_seconds:.1f} s total "
              f"({write_seconds / wall_seconds * 100:.1f}% of wall time), {written_mb:.1f} MB on disk")

    if tracker.snapshots:
        print(f"Peak memory      : {max(s.rss_mb for s in tracker.snapshots):.0f} MB")
    print("=============================================")


def write_results_spreadsheet(tasks, results, tracker: DiagnosticTracker, out_path: Path) -> None:
    """Write the run to an .xlsx with two sheets.

    summary  - one row per analysis: which registry it came from, dataset,
               operator, status, feature count, the headline measure (+ its unit),
               how long it took, where the spatial output went, and the error for
               anything that failed.
    features - one row per matched feature: its id, its own measure (distance /
               overlap / shared border), and the report fields (aggregate_columns)
               as text.
    """
    dataset_snaps = [s for s in tracker.snapshots if s.step in ("dataset_done", "dataset_failed")]

    summary_rows = []
    feature_rows = []
    for i, (task, group) in enumerate(zip(tasks, results.results)):
        snap = dataset_snaps[i] if i < len(dataset_snaps) else None
        seconds = snap.extra.get("seconds") if snap else None
        result = group.results[0] if group.results else None

        summary_rows.append({
            "registry": task.source_registry,
            "dataset": task.dataset_name,
            "datasource": task.datasource,
            "source": task.source_type,
            "operator": task.operator,
            "status": group.status,
            "features": result.feature_count if result else 0,
            "measure_value": result.measure_value if result else None,
            "measure_unit": result.measure_unit if result else None,
            "seconds": seconds,
            "spatial_link": result.spatial_link if result else None,
            "error": group.error,
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
    time_adapter_reads()

    registries = load_registries(args.registry, args.ignore_os_check)
    tasks = build_tasks(registries)
    print(f"Total analyses to run: {len(tasks)}")

    if args.spatial_out:
        warn_about_duplicate_outputs(tasks)

    tracker = DiagnosticTracker(jsonl_path=Path(args.jsonl) if args.jsonl else None)
    settings = Settings(
        record_spatial=bool(args.spatial_out),
        temp_dir=args.spatial_out,
    )
    print(f"Spatial export: {'on -> ' + args.spatial_out if args.spatial_out else 'off'}")

    # The connection is opened before the AOI is built, because a Tantalis AOI is
    # read over that same connection. Building the AOI is timed separately from
    # the run, so a slow Tantalis lookup never lands in the per-dataset numbers.
    connection = get_oracle_connection(tasks, needed_for_aoi=uses_tantalis_aoi(args))
    try:
        aoi = build_aoi(args, connection)

        start = time.perf_counter()
        results = run_analysis(
            aoi=aoi,
            tasks=tasks,
            job_id=args.job_id,
            oracle_connection=connection,
            tracker=tracker,
            settings=settings,
        )
        wall = time.perf_counter() - start
    finally:
        if connection is not None:
            connection.close()

    print_run_summary(tasks, results, tracker, wall, spatial_on=bool(args.spatial_out))
    print(f"\nAssembled AstResults: {len(results.results)} dataset groups, job_id={results.job_id}")

    out_path = Path(args.out)
    write_results_spreadsheet(tasks, results, tracker, out_path)
    print(f"Results spreadsheet written to {out_path.resolve()}")


if __name__ == "__main__":
    main()
