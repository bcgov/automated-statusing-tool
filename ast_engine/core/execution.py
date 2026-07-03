"""
Execution orchestrator: AOI -> dataset registry -> adapter -> operator -> results.

For one AOI, this runs each dataset's analysis and assembles a single AstResults.
It is the glue between the four pieces that are already built:

  - adapters (Oracle / file) read features for an AOI;
  - operators (overlay / proximity / adjacency) compute one result per dataset;
  - the registry says, per dataset, which analysis to run and with what params;
  - the results model collects everything into AstResults.

The orchestrator runs on its own small AnalysisTask object, not on the registry
model directly, so it is insulated from registry-shape changes. A thin mapper
turns each registry dataset into an AnalysisTask; the run loop never changes when
the registry shape settles. The same mapper handles every registry the same way
- provincial, regional, Tab 1 and user - so a run is just the concatenation of
their tasks (see tasks_from_registries).

The driver itself (run_analysis) has no knowledge of the registry: it takes a
list of AnalysisTask and a built AreaOfInterest, picks the right adapter per task,
calls the operator, and records one DatasetResultGroup per dataset. One dataset's
failure is logged and recorded as an empty group - the run continues, because a
real run covers 50-100 datasets per AOI.
"""

from __future__ import annotations

import getpass
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from .aoi import AreaOfInterest
from .data_adapters.base import BaseSpatialAdapter
from .data_adapters.file.adapter import FileSpatialAdapter
from .data_adapters.oracle import OracleAdapter, OracleConnection
from .operator import adjacent, overlay, proximity
from .results import AnalysisResult, AstResults, DatasetResultGroup
from ..utils.diagnostics import DiagnosticTracker

logger = logging.getLogger(__name__)

# Analysis names, shared 1:1 with the registry operator block (operator.type)
# and the operator functions.
OVERLAY = "overlay"
WITHIN_DISTANCE = "within_distance"
NEAREST = "nearest"
ADJACENCY = "adjacency"

# Source types, from the registry data_adapter value (lower-cased).
ORACLE = "oracle"
FILE = "file"


@dataclass
class AnalysisTask:
    """One analysis to run for one dataset.

    The orchestrator's own per-dataset job. It carries only what the run loop
    needs, so it does not move when the registry model changes. Fields map
    straight onto an operator call.

    source_type      "oracle" or "file" - picks the adapter.
    datasource       the table ("SCHEMA.TABLE") for Oracle, or the full file path
                     (the layer, if any, is part of the path) for file datasets.
    operator         which analysis: overlay / within_distance / nearest / adjacency.
    geom_type        point / line / polygon - selects the overlay result subtype.
    distance_m / k / max_distance_m / tolerance_m   the per-operator parameters.
    feature_id_field the column that identifies a feature (the registry unique_id);
                     None falls back to the row index.
    keep_properties  the report fields (the registry aggregate_columns).
    where            the dataset's structured attribute filter (definition query);
                     pushed down so only matching features are read.
    source_registry  which registry file the dataset came from (provenance only).
    """

    dataset_id: str
    dataset_name: str
    source_type: str
    datasource: str
    operator: str
    geom_type: Optional[str] = None
    distance_m: Optional[float] = None
    k: Optional[int] = None
    max_distance_m: Optional[float] = None
    tolerance_m: Optional[float] = None
    feature_id_field: Optional[str] = None
    keep_properties: list[str] = field(default_factory=list)
    where: Any = None
    source_registry: Optional[str] = None


# ---------------------------------------------------------------------------
# Registry -> tasks (the only place that touches the registry model)
# ---------------------------------------------------------------------------

def tasks_from_registries(registries: Iterable[tuple[str, Any]]) -> list[AnalysisTask]:
    """Build one task list from several registries (provincial + regional + Tab 1
    + user), in order.

    Registries are authored not to overlap - even when two entries point at the
    same datasource they apply different filters and are distinct analyses that
    should both run - so combining them is a plain append: no precedence, no
    dedup. Each item is a (name, Registry) pair; the name is recorded on every
    task as provenance.
    """
    tasks: list[AnalysisTask] = []
    for name, registry in registries:
        tasks.extend(tasks_from_registry(registry, source_registry=name))
    return tasks


def tasks_from_registry(registry: Any, source_registry: Optional[str] = None) -> list[AnalysisTask]:
    """Map one registry's datasets to AnalysisTasks.

    A dataset that cannot be mapped (e.g. no operator block) is logged and
    skipped, so one bad row does not stop the rest of the registry.
    """
    tasks: list[AnalysisTask] = []
    for dataset in registry.datasets:
        try:
            tasks.append(_task_from_dataset(dataset, source_registry))
        except Exception:
            logger.exception(
                "Skipping dataset %r: could not build an analysis task",
                getattr(dataset, "name", "?"),
            )
    return tasks


def _task_from_dataset(dataset: Any, source_registry: Optional[str]) -> AnalysisTask:
    """Turn one RegistryDataset into an AnalysisTask.

    The operator block (operator.type + its params) drives which analysis runs.
    geometry_type is lower-cased so it matches the overlay result subtypes
    (point / line / polygon). The structured `where` filter and the report fields
    (aggregate_columns) travel straight through.
    """
    op = dataset.operator
    if op is None:
        raise ValueError(f"dataset {dataset.name!r} has no operator block")

    return AnalysisTask(
        dataset_id=str(dataset.id),
        dataset_name=dataset.name,
        source_type=str(dataset.data_adapter).lower(),
        datasource=dataset.datasource,
        operator=op.type,
        geom_type=(str(dataset.geometry_type).lower() or None) if dataset.geometry_type else None,
        distance_m=getattr(op, "distance_m", None),
        k=getattr(op, "k", None),
        max_distance_m=getattr(op, "max_distance_m", None),
        tolerance_m=getattr(op, "tolerance_m", None),
        feature_id_field=dataset.unique_id,
        keep_properties=list(dataset.aggregate_columns or []),
        where=dataset.where,
        source_registry=source_registry,
    )


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def run_analysis(
    *,
    aoi: AreaOfInterest,
    tasks: Iterable[AnalysisTask],
    job_id: str,
    oracle_connection: Optional[OracleConnection] = None,
    tracker: Optional[DiagnosticTracker] = None,
) -> AstResults:
    """Run every task for one AOI and return the assembled AstResults.

    If any task reads from Oracle and no connection is passed, one BCGW
    connection is opened from the BCGW_USER / BCGW_PASSWORD / BCGW_HOST
    environment variables (else prompted) and closed at the end. A connection
    passed in is reused and left open (the caller owns it). One adapter of each
    kind is reused across all tasks.

    Per-dataset timings are logged through the DiagnosticTracker so a run can be
    profiled (which datasets are slow, where parallelism would help).
    """
    tasks = list(tasks)
    tracker = tracker or DiagnosticTracker()
    file_adapter = FileSpatialAdapter()

    oracle_adapter, owned_connection = _resolve_oracle_adapter(tasks, oracle_connection)

    timings: list[tuple[str, float]] = []
    try:
        tracker.log("run_start", job_id=job_id, aoi_id=aoi.aoi_id, task_count=len(tasks))
        groups = [
            _run_one_task(task, aoi, file_adapter, oracle_adapter, tracker, timings)
            for task in tasks
        ]
        _log_timing_summary(timings, tracker)
        return AstResults(job_id=job_id, aoi_id=aoi.aoi_id, results=groups)
    finally:
        if owned_connection is not None:
            owned_connection.close()


def _resolve_oracle_adapter(
    tasks: list[AnalysisTask],
    oracle_connection: Optional[OracleConnection],
) -> tuple[Optional[OracleAdapter], Optional[OracleConnection]]:
    """Pick the Oracle adapter and say whether we own its connection.

    Returns (adapter, owned_connection). owned_connection is non-None only when
    we opened it here and must close it ourselves; a caller-supplied connection
    is reused and returned as None so it is left open.
    """
    if oracle_connection is not None:
        return OracleAdapter(oracle_connection.connection, oracle_connection.cursor), None

    if any(task.source_type == ORACLE for task in tasks):
        connection = _open_oracle_connection()
        return OracleAdapter(connection.connection, connection.cursor), connection

    return None, None


def _run_one_task(
    task: AnalysisTask,
    aoi: AreaOfInterest,
    file_adapter: FileSpatialAdapter,
    oracle_adapter: Optional[OracleAdapter],
    tracker: DiagnosticTracker,
    timings: list[tuple[str, float]],
) -> DatasetResultGroup:
    """Run one task and wrap its result in a DatasetResultGroup.

    A failure is logged and recorded as an empty group so the run continues.
    """
    start = time.perf_counter()
    try:
        adapter = _pick_adapter(task, file_adapter, oracle_adapter)
        result = _run_operator(task, aoi, adapter)
        elapsed = time.perf_counter() - start
        timings.append((task.dataset_name, elapsed))
        tracker.log(
            "dataset_done",
            dataset=task.dataset_name,
            operator=task.operator,
            source=task.source_type,
            features=result.feature_count,
            seconds=round(elapsed, 3),
        )
        return DatasetResultGroup(
            dataset_id=task.dataset_id,
            dataset_name=task.dataset_name,
            results=[result],
        )
    except Exception:
        elapsed = time.perf_counter() - start
        timings.append((task.dataset_name, elapsed))
        logger.exception(
            "Analysis failed for dataset %r (%s); recording an empty result and continuing",
            task.dataset_name,
            task.datasource,
        )
        tracker.log(
            "dataset_failed",
            dataset=task.dataset_name,
            operator=task.operator,
            source=task.source_type,
            seconds=round(elapsed, 3),
        )
        return DatasetResultGroup(
            dataset_id=task.dataset_id,
            dataset_name=task.dataset_name,
            results=[],
        )


def _pick_adapter(
    task: AnalysisTask,
    file_adapter: FileSpatialAdapter,
    oracle_adapter: Optional[OracleAdapter],
) -> BaseSpatialAdapter:
    """Pick the reused adapter for a task's source type."""
    if task.source_type == FILE:
        return file_adapter
    if task.source_type == ORACLE:
        if oracle_adapter is None:
            raise RuntimeError(
                f"dataset {task.dataset_name!r} needs an Oracle connection but none is available"
            )
        return oracle_adapter
    raise ValueError(
        f"unknown source type {task.source_type!r} for dataset {task.dataset_name!r}"
    )


def _source_kwargs(task: AnalysisTask) -> dict[str, str]:
    """Dataset identity for the adapter read: table for Oracle, path for files."""
    if task.source_type == ORACLE:
        return {"table": task.datasource}
    return {"path": task.datasource}


def _run_operator(task: AnalysisTask, aoi: AreaOfInterest, adapter: BaseSpatialAdapter) -> AnalysisResult:
    """Dispatch a task to its operator and return the typed result.

    The orchestrator passes params + ids + the attribute filter; each operator
    builds its own SpatialFilter and ReadOptions.
    """
    common = dict(
        aoi=aoi,
        adapter=adapter,
        feature_id_field=task.feature_id_field,
        keep_properties=task.keep_properties or None,
        where=task.where,
        **_source_kwargs(task),
    )

    if task.operator == OVERLAY:
        return overlay.intersection(geom_type=task.geom_type, **common)
    if task.operator == WITHIN_DISTANCE:
        if task.distance_m is None:
            raise ValueError(f"within_distance needs distance_m (dataset {task.dataset_name!r})")
        return proximity.within_distance(distance_m=task.distance_m, **common)
    if task.operator == NEAREST:
        return proximity.nearest(k=task.k or 1, max_distance_m=task.max_distance_m, **common)
    if task.operator == ADJACENCY:
        return adjacent.adjacency(tolerance_m=task.tolerance_m or 0, **common)
    raise ValueError(f"unknown operator {task.operator!r} for dataset {task.dataset_name!r}")


# ---------------------------------------------------------------------------
# Oracle connection (mirrors spreadsheet_ingestion's credential pattern)
# ---------------------------------------------------------------------------

def _open_oracle_connection() -> OracleConnection:
    """Open one BCGW connection from env vars, falling back to a prompt.

    Credentials come from BCGW_USER / BCGW_PASSWORD / BCGW_HOST; the password is
    read with getpass so it never echoes. Same pattern as the registry build.
    """
    user = os.environ.get("BCGW_USER") or input("BCGW username: ").strip()
    password = os.environ.get("BCGW_PASSWORD") or getpass.getpass("BCGW password: ")
    host = os.environ.get("BCGW_HOST") or input(
        "BCGW host/DSN (e.g. bcgw.bcgov:1521/idwprod1.bcgov): "
    ).strip()
    if not (user and password and host):
        raise RuntimeError(
            "Missing BCGW credentials; set BCGW_USER / BCGW_PASSWORD / BCGW_HOST"
        )
    return OracleConnection(user, password, host)


def _log_timing_summary(timings: list[tuple[str, float]], tracker: DiagnosticTracker) -> None:
    """Log total time and the slowest datasets - input for the efficiency /
    parallelization discussion."""
    if not timings:
        return
    total = sum(seconds for _, seconds in timings)
    slowest = sorted(timings, key=lambda item: item[1], reverse=True)[:5]
    tracker.log(
        "run_complete",
        dataset_count=len(timings),
        total_seconds=round(total, 2),
        slowest=[(name, round(seconds, 3)) for name, seconds in slowest],
    )
