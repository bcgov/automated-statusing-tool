# ast_engine/utils/diagnostics.py
import json
import logging
import os
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Any
import psutil

# Using the standard library logging hierarchy
logger = logging.getLogger("ast-engine.diagnostics")

MB = 1024 * 1024

@dataclass
class DiagnosticSnapshot:
    timestamp: str
    step: str
    rss_mb: float
    vms_mb: float
    elapsed_s: float
    extra: dict[str, Any] = field(default_factory=dict)

class DiagnosticTracker:
    def __init__(self, jsonl_path: Path | None = None):
        self.process = psutil.Process(os.getpid())
        self.run_start = time.perf_counter()
        self.jsonl_path = jsonl_path
        self.snapshots: list[DiagnosticSnapshot] = []

    def capture(self, step: str, **extra: Any) -> DiagnosticSnapshot:
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
        """Logs via the standard logger and optionally appends to JSONL."""
        snap = self.capture(step, **extra)

        # formatting handeled by logger
        logger.info(
            "step=%s | rss_mb=%.1f | vms_mb=%.1f | elapsed_s=%.2f | extra=%s",
            snap.step,
            snap.rss_mb,
            snap.vms_mb,
            snap.elapsed_s,
            snap.extra,
        )

        # Optional structured JSONL output
        if self.jsonl_path:
            with self.jsonl_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(snap)) + "\n")