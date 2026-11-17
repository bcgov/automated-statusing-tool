"""
Map layers for a run: the link between the engine's results and the map generator.

The map generator (html_maps.py) knows nothing about registries, tasks or
results - it is handed a list of MapLayer. This module builds that list from
what a run already has: the tasks say what each dataset is called and which
fields to report, and the results say where the run saved each dataset's
features.
"""

from pathlib import Path
from typing import Sequence

from ast_engine.core.execution import AnalysisTask
from ast_engine.core.results import AstResults

from .html_maps import MapLayer

# The group a task is mapped under when it has no category and came from no registry.
UNGROUPED = "datasets"


def build_map_layers(tasks: Sequence[AnalysisTask], results: AstResults) -> list[MapLayer]:
    """Build one MapLayer per dataset the run saved features for.

    tasks and results.results line up one to one, in order: run_analysis
    returns one result group per task.

    A dataset is left out when it has no saved features - it failed, it found
    nothing, or the run was not saving its spatial output (record_spatial).
    """
    layers: list[MapLayer] = []
    for task, group in zip(tasks, results.results, strict=True):
        paths = tuple(
            Path(part.result.spatial_link)
            for part in group.parts
            if part.result.spatial_link
        )
        if not paths:
            continue
        layers.append(
            MapLayer(
                title=task.dataset_name,
                group=task.category or task.source_registry or UNGROUPED,
                datasource=task.datasource,
                paths=paths,
                summarize_fields=tuple(task.keep_properties),
                buffer_m=task.distance_m,
                key=task.dataset_id,
            )
        )
    return layers
