"""Tests for building the map layers of a run from its tasks and results."""

from pathlib import Path
from uuid import uuid4

import pytest

from ast_engine.config.registry.models import DataAdapter
from ast_engine.core.execution import AnalysisTask
from ast_engine.core.results import (
    AOIPartResult,
    AstResults,
    DatasetResultGroup,
    PolyOverlayResult,
    ProximityResult,
)
from ast_engine.reporting.job_maps import UNGROUPED, build_map_layers

pytestmark = pytest.mark.unit


def _task(name: str, **overrides) -> AnalysisTask:
    values = {
        "dataset_id": name,
        "dataset_name": name,
        "source_type": DataAdapter.ORACLE,
        "datasource": f"WHSE.{name.upper()}",
        "operator": "overlay",
    }
    values.update(overrides)
    return AnalysisTask(**values)


def _group(name: str, *spatial_links, result_type=PolyOverlayResult, **result_fields) -> DatasetResultGroup:
    """A dataset's result group, with one AOI part per spatial link given."""
    parts = [
        AOIPartResult(
            aoi_part_id=f"aoi_part_{index}",
            part_index=index,
            part_area_ha=1.0,
            result=result_type(spatial_link=link, **result_fields),
        )
        for index, link in enumerate(spatial_links, start=1)
    ]
    return DatasetResultGroup(dataset_id=name, dataset_name=name, parts=parts)


def _results(*groups: DatasetResultGroup) -> AstResults:
    return AstResults(job_id=uuid4(), aoi_id="aoi", results=list(groups))


def test_a_dataset_becomes_a_layer_over_its_saved_features():
    task = _task("Parks", keep_properties=["PARK_CLASS", "PARK_NAME"], source_registry="provincial")
    results = _results(_group("Parks", "/work/Parks_part_1.gpkg", "/work/Parks_part_2.gpkg", total_area=1.0))

    [layer] = build_map_layers([task], results)

    assert layer.title == "Parks"
    assert layer.group == "provincial"
    assert layer.datasource == "WHSE.PARKS"
    assert layer.paths == (Path("/work/Parks_part_1.gpkg"), Path("/work/Parks_part_2.gpkg"))
    assert layer.summarize_fields == ("PARK_CLASS", "PARK_NAME")
    assert layer.buffer_m is None


def test_a_within_distance_dataset_carries_its_search_distance():
    task = _task("Wells", operator="within_distance", distance_m=500.0)
    results = _results(_group("Wells", "/work/Wells_part_1.gpkg", result_type=ProximityResult))

    [layer] = build_map_layers([task], results)

    assert layer.buffer_m == 500.0


def test_a_dataset_with_no_saved_features_is_left_out():
    """It failed, it found nothing, or the run was not saving spatial output."""
    tasks = [_task("Failed"), _task("Empty"), _task("Parks")]
    results = _results(
        DatasetResultGroup(dataset_id="Failed", dataset_name="Failed", status="failure", parts=[]),
        _group("Empty", None, total_area=0.0),
        _group("Parks", "/work/Parks_part_1.gpkg", total_area=1.0),
    )

    assert [layer.title for layer in build_map_layers(tasks, results)] == ["Parks"]


def test_a_task_built_by_hand_is_mapped_under_a_default_group():
    results = _results(_group("Parks", "/work/Parks_part_1.gpkg", total_area=1.0))

    [layer] = build_map_layers([_task("Parks")], results)

    assert layer.group == UNGROUPED


def test_tasks_and_results_must_line_up():
    with pytest.raises(ValueError):
        build_map_layers([_task("Parks"), _task("Wells")], _results(_group("Parks", None, total_area=0.0)))
