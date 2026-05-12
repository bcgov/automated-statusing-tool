# %%
"""
Lightweight diagnostics and runtime tracking utilities.

This module provides:
    - Standardized console/file logging
    - Runtime diagnostics snapshots
    - Memory usage tracking
    - Elapsed runtime tracking
    - Optional JSONL diagnostics export

Intended use:
    - Geospatial ETL pipelines
    - Long-running raster/vector processing
    - Batch orchestration scripts
    - Notebook experimentation
"""

# -----------------------------------------------------------------------------
# Imports
# -----------------------------------------------------------------------------

import json
import logging
import os
import time

from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Any

import psutil


# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------

MB = 1024 * 1024


# -----------------------------------------------------------------------------
# Diagnostic Snapshot
# -----------------------------------------------------------------------------

@dataclass
class DiagnosticSnapshot:
    """
    Container for a single diagnostic snapshot.

    Attributes
    ----------
    timestamp : str
        ISO timestamp when the snapshot was captured.

    step : str
        Human-readable name of the processing step.

    rss_mb : float
        Resident memory usage in MB.

    vms_mb : float
        Virtual memory usage in MB.

    elapsed_s : float
        Seconds elapsed since tracker initialization.

    extra : dict[str, Any]
        Optional metadata attached to the snapshot.
    """

    timestamp: str
    step: str
    rss_mb: float
    vms_mb: float
    elapsed_s: float
    extra: dict[str, Any] = field(default_factory=dict)


# -----------------------------------------------------------------------------
# Diagnostic Tracker
# -----------------------------------------------------------------------------

class DiagnosticTracker:
    """
    Lightweight runtime diagnostics tracker.

    Tracks:
        - Memory usage
        - Elapsed runtime
        - Named processing steps
        - Optional structured JSONL output

    Parameters
    ----------
    logger : logging.Logger
        Configured logger instance.

    output_file : Path | None
        Optional JSONL diagnostics output path.
    """

    def __init__(
        self,
        logger: logging.Logger,
        output_file: Path | None = None,
    ):
        self.logger = logger
        self.output_file = output_file

        # Current Python process
        self.process = psutil.Process(os.getpid())

        # High precision runtime counter
        self.run_start = time.perf_counter()

        # In-memory diagnostic snapshots
        self.snapshots: list[DiagnosticSnapshot] = []

    def capture(self, step: str, **extra: Any) -> DiagnosticSnapshot:
        """
        Capture a diagnostic snapshot without logging it.

        Parameters
        ----------
        step : str
            Name of the processing step.

        **extra : Any
            Additional metadata to attach.

        Returns
        -------
        DiagnosticSnapshot
        """

        mem = self.process.memory_info()

        snap = DiagnosticSnapshot(
            timestamp=datetime.now().isoformat(timespec="seconds"),
            step=step,
            rss_mb=mem.rss / MB,
            vms_mb=mem.vms / MB,
            elapsed_s=time.perf_counter() - self.run_start,
            extra=extra,
        )

        self.snapshots.append(snap)

        return snap

    def log(self, step: str, **extra: Any) -> None:
        """
        Capture and immediately log a diagnostic snapshot.

        Parameters
        ----------
        step : str
            Name of the processing step.

        **extra : Any
            Additional metadata to attach.
        """

        snap = self.capture(step, **extra)

        # Standard logger output
        self.logger.info(
            "step=%s | rss_mb=%.1f | vms_mb=%.1f | elapsed_s=%.2f | extra=%s",
            snap.step,
            snap.rss_mb,
            snap.vms_mb,
            snap.elapsed_s,
            snap.extra,
        )

        # Optional JSONL structured output
        if self.output_file:
            with self.output_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(snap)) + "\n")


# -----------------------------------------------------------------------------
# Logger Setup
# -----------------------------------------------------------------------------

def setup_logger(
    log_file: Path,
    logger_name: str = "AST",
) -> logging.Logger:
    """
    Create a logger that writes to both console and file.

    Safe to call multiple times without duplicating handlers.

    Parameters
    ----------
    log_file : Path
        Path to the output log file.

    logger_name : str
        Name of the logger instance.

    Returns
    -------
    logging.Logger
    """

    logger = logging.getLogger(logger_name)

    logger.setLevel(logging.INFO)
    logger.propagate = False

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Prevent duplicate handlers during notebook reruns
    if logger.handlers:
        logger.handlers.clear()

    # File output
    file_handler = logging.FileHandler(
        log_file,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    # Console output
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)

    return logger


# -----------------------------------------------------------------------------
# Example Orchestration Usage
# -----------------------------------------------------------------------------

"""
Example usage inside an orchestration script:

from pathlib import Path

from utils.diagnostics import (
    setup_logger,
    DiagnosticTracker,
)

# -------------------------------------------------------------------------
# Setup paths
# -------------------------------------------------------------------------

log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)

log_file = log_dir / "run.log"
diag_file = log_dir / "diagnostics.jsonl"

# -------------------------------------------------------------------------
# Setup logger and diagnostics tracker
# -------------------------------------------------------------------------

logger = setup_logger(log_file)

diag = DiagnosticTracker(
    logger=logger,
    output_file=diag_file,
)

# -------------------------------------------------------------------------
# Example orchestration workflow
# -------------------------------------------------------------------------

diag.log(
    "script_initialized",
    analysis_year=2025,
    tsa_id=72,
)

diag.log(
    "extract_started",
)

# Run extraction process
extract_data()

diag.log(
    "extract_finished",
    features=194222,
)

diag.log(
    "rasterization_started",
)

# Run raster processing
build_rasters()

diag.log(
    "rasterization_finished",
    output_cells=12839222,
)

diag.log(
    "script_complete",
)

"""