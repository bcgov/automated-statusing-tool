"""
Report rows for a run: the link between the engine's results and the report writer.

The report writer (conflicts_report.py) knows nothing about registries, tasks or
results - it is handed a ReportHeader and a list of DatasetReport. This module
builds those from what a run already has: the tasks say what each dataset is
called, where it came from and which fields to report, and the results say
whether it ran and what it found for each part of the AOI.
"""

from typing import Iterable, Mapping, Optional, Sequence

import geopandas as gpd
import pandas as pd

from ast_engine.core.execution import AnalysisTask
from ast_engine.core.results import AstResults

from .conflicts_report import DatasetReport, PartOutcome, summary_values

# The heading a dataset is listed under when it has no category and came from
# no registry.
UNCATEGORIZED = "Datasets"


def build_dataset_reports(
    tasks: Sequence[AnalysisTask],
    results: AstResults,
    *,
    map_links: Optional[Mapping[str, str]] = None,
    exclude_registries: Iterable[str] = (),
) -> list[DatasetReport]:
    """Build one DatasetReport per dataset the run checked, in the run's order.

    tasks and results.results line up one to one, in order: run_analysis
    returns one result group per task.

    map_links           where each dataset's map is, keyed by dataset id; a
                        dataset that is not in it gets no map link.
    exclude_registries  registries whose datasets are left off the report. Tab 1
                        is one: its datasets belong on the status sheet's first
                        tabs, not among the conflicts.

    A dataset that has no category is listed under the name of its registry.
    """
    map_links = map_links or {}
    excluded = set(exclude_registries)

    reports: list[DatasetReport] = []
    for task, group in zip(tasks, results.results, strict=True):
        if task.source_registry in excluded:
            continue
        reports.append(
            DatasetReport(
                category=task.category or task.source_registry or UNCATEGORIZED,
                name=task.dataset_name,
                datasource=task.datasource,
                definition_query=task.definition_query,
                failed=group.status == "failure",
                parts=tuple(
                    PartOutcome(
                        feature_count=part.result.feature_count,
                        values=summary_values(
                            (feature.properties for feature in part.result.features),
                            task.keep_properties,
                        ),
                    )
                    for part in group.parts
                ),
                map_link=map_links.get(task.dataset_id),
            )
        )
    return reports


def aoi_part_names(aoi_gdf: gpd.GeoDataFrame) -> tuple[str, ...]:
    """A name for each part of the AOI, in order, for the report's part headings.

    A part is one row of the AOI. It is named by the row's own values - the
    dissolve field value that tells the parts apart, e.g. "BLOCK = A" - or
    "Part 1", "Part 2"... when the rows carry no values.
    """
    geometry_column = aoi_gdf.geometry.name
    names = []
    for position, (_, row) in enumerate(aoi_gdf.iterrows(), start=1):
        values = [
            f"{column} = {value}"
            for column, value in row.drop(labels=[geometry_column]).items()
            if value is not None and not pd.isna(value)
        ]
        names.append(", ".join(values) or f"Part {position}")
    return tuple(names)
