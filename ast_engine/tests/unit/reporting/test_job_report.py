"""Tests for building the report rows of a run from its tasks and results."""

from uuid import uuid4

import geopandas as gpd
import pytest
from shapely.geometry import box

from ast_engine.config.registry.models import DataAdapter
from ast_engine.core.execution import AnalysisTask
from ast_engine.core.results import (
    AOIPartResult,
    AstResults,
    DatasetResultGroup,
    FeatureRecord,
    PointOverlayResult,
)
from ast_engine.reporting.job_report import UNCATEGORIZED, aoi_part_names, build_dataset_reports

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


def _group(name: str, *parts: list[dict]) -> DatasetResultGroup:
    """A dataset's result group: one AOI part per list of feature properties."""
    return DatasetResultGroup(
        dataset_id=name,
        dataset_name=name,
        parts=[
            AOIPartResult(
                aoi_part_id=f"aoi_part_{index}",
                part_index=index,
                part_area_ha=1.0,
                result=PointOverlayResult(
                    features=[
                        FeatureRecord(feature_id=str(number), properties=properties)
                        for number, properties in enumerate(features)
                    ],
                ),
            )
            for index, features in enumerate(parts, start=1)
        ],
    )


def _results(*groups: DatasetResultGroup) -> AstResults:
    return AstResults(job_id=uuid4(), aoi_id="aoi", results=list(groups))


def test_a_dataset_is_reported_with_what_it_found():
    task = _task(
        "Parks",
        category="Critical Conflicts",
        definition_query="CLASS <> 'X'",
        keep_properties=["CLASS"],
        source_registry="common",
    )
    results = _results(_group("Parks", [{"CLASS": "B"}, {"CLASS": "A"}, {"CLASS": "B"}]))

    [report] = build_dataset_reports([task], results, map_links={"Parks": "maps/common__Parks.html"})

    assert report.category == "Critical Conflicts"
    assert report.name == "Parks"
    assert report.datasource == "WHSE.PARKS"
    assert report.definition_query == "CLASS <> 'X'"
    assert report.failed is False
    assert report.parts[0].feature_count == 3
    assert report.parts[0].values == ("A", "B")
    assert report.map_link == "maps/common__Parks.html"


def test_a_failed_dataset_is_reported_as_failed():
    results = _results(DatasetResultGroup(dataset_id="Parks", dataset_name="Parks", status="failure", parts=[]))

    [report] = build_dataset_reports([_task("Parks")], results)

    assert report.failed is True
    assert report.parts == ()


def test_a_dataset_without_a_category_is_listed_under_its_registry():
    results = _results(_group("Parks", []), _group("Wells", []))
    tasks = [_task("Parks", source_registry="one_status_common_datasets"), _task("Wells")]

    reports = build_dataset_reports(tasks, results)

    assert [report.category for report in reports] == ["one_status_common_datasets", UNCATEGORIZED]


def test_an_aoi_part_gets_its_own_outcome():
    task = _task("Parks", keep_properties=["CLASS"])
    results = _results(_group("Parks", [{"CLASS": "A"}], []))

    [report] = build_dataset_reports([task], results)

    assert [part.feature_count for part in report.parts] == [1, 0]
    assert [part.values for part in report.parts] == [("A",), ()]


def test_datasets_of_an_excluded_registry_are_left_out():
    tasks = [_task("Parks", source_registry="common"), _task("District", source_registry="tab1")]
    results = _results(_group("Parks", []), _group("District", []))

    reports = build_dataset_reports(tasks, results, exclude_registries=["tab1"])

    assert [report.name for report in reports] == ["Parks"]


def test_aoi_parts_are_named_by_their_values():
    aoi = gpd.GeoDataFrame(
        {"BLOCK": ["A", "B"]},
        geometry=[box(0, 0, 1, 1), box(2, 0, 3, 1)],
        crs="EPSG:3005",
    )

    assert aoi_part_names(aoi) == ("BLOCK = A", "BLOCK = B")


def test_an_aoi_with_no_values_has_numbered_parts():
    aoi = gpd.GeoDataFrame(geometry=[box(0, 0, 1, 1)], crs="EPSG:3005")

    assert aoi_part_names(aoi) == ("Part 1",)
