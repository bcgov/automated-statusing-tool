"""Tests for building the Crown Land Status tab's contents from a run."""

from datetime import date
from uuid import uuid4

import pytest

from ast_engine.config.registry.models import DataAdapter
from ast_engine.core.execution import AnalysisTask
from ast_engine.core.results import (
    AOIPartResult,
    AdjacencyResult,
    AstResults,
    DatasetResultGroup,
    FeatureRecord,
    PolyOverlayResult,
    ProximityResult,
)
from ast_engine.reporting import job_status
from ast_engine.reporting.job_status import TenureFacts, build_crown_land_status

pytestmark = pytest.mark.unit

RUN_DATE = date(2026, 3, 31)


def _task(datasource: str, operator: str = "overlay", registry: str = "tab1") -> AnalysisTask:
    return AnalysisTask(
        dataset_id=f"{datasource}:{operator}",
        dataset_name=datasource,
        source_type=DataAdapter.ORACLE,
        datasource=datasource,
        operator=operator,
        source_registry=registry,
    )


def _features(*items) -> list[FeatureRecord]:
    """Features from (properties, measure) pairs, or from properties alone."""
    features = []
    for number, item in enumerate(items):
        properties, measure = item if isinstance(item, tuple) else (item, None)
        features.append(FeatureRecord(feature_id=str(number), properties=properties, measure=measure))
    return features


def _group(result, failed: bool = False) -> DatasetResultGroup:
    parts = [] if failed else [AOIPartResult(aoi_part_id="aoi_part_1", part_index=1, part_area_ha=1.0, result=result)]
    return DatasetResultGroup(
        dataset_id="x", dataset_name="x", status="failure" if failed else "success", parts=parts,
    )


def _overlay(*items) -> DatasetResultGroup:
    return _group(PolyOverlayResult(features=_features(*items), total_area=1.0))


def _build(tasks, groups, **options):
    results = AstResults(job_id=uuid4(), aoi_id="aoi", results=list(groups))
    return build_crown_land_status(tasks, results, tab1_registry="tab1", run_date=RUN_DATE, **options)


def test_a_line_lists_the_values_found_sorted_and_once_each():
    status = _build(
        [_task(job_status.MAPSHEETS)],
        [_overlay({"MAP_TILE_DISPLAY_NAME": "092P.046"}, {"MAP_TILE_DISPLAY_NAME": "092P.045"},
                  {"MAP_TILE_DISPLAY_NAME": "092P.046"})],
    )

    assert status.mapsheets == ("092P.045", "092P.046")


def test_a_line_built_from_two_fields_joins_them():
    status = _build(
        [_task(job_status.SURVEY_PARCELS)],
        [_overlay({"PIN_SID": 1234.0, "PARCEL_LEGAL_DESCRIPTION": "DISTRICT LOT 1"})],
    )

    assert status.pins == ("1234 - DISTRICT LOT 1",)


def test_the_same_table_run_two_ways_feeds_two_lines():
    """Survey parcels are overlaid for "PIN Intersects" and checked for
    adjacency for "PIN Adjacent"."""
    tasks = [_task(job_status.SURVEY_PARCELS, "overlay"), _task(job_status.SURVEY_PARCELS, "adjacency")]
    groups = [
        _overlay({"PIN_SID": 1, "PARCEL_LEGAL_DESCRIPTION": "INSIDE"}),
        _group(AdjacencyResult(is_adjacent=True, features=_features(({"PIN_SID": 2, "PARCEL_LEGAL_DESCRIPTION": "BESIDE"}, 40.0)))),
    ]

    status = _build(tasks, groups)

    assert status.pins == ("1 - INSIDE",)
    assert status.pins_adjacent == ("2 - BESIDE",)


def test_provincial_forest_lines_read_their_own_fields():
    features = {"PROV_FOREST_CD_DESCRIPTION": "Addition", "OIC_YEAR": 1995, "OIC_NUMBER": "123", "MAP_BLOCK_ID": "B7"}

    status = _build([_task(job_status.PROV_FOREST_ADDITION)], [_overlay(features)])

    assert status.provincial_forest_addition == ("Addition - 1995",)
    assert status.provincial_forest_addition2 == ("123 - B7",)


@pytest.mark.parametrize("features, expected", [([{}], "Yes"), ([], "No")])
def test_alr_is_yes_or_no(features, expected):
    assert _build([_task(job_status.ALR)], [_overlay(*features)]).in_alr == expected


def test_nearest_indian_reserve_is_named_with_its_distance_in_km():
    group = _group(ProximityResult(features=_features(({"ENGLISH_NAME": "CANIM LAKE 1", "BAND_NAME": "CANIM LAKE"}, 12_340.0))))

    status = _build([_task(job_status.INDIAN_RESERVES, "nearest")], [group])

    assert status.nearest_indian_reserve == "CANIM LAKE 1 - CANIM LAKE | 12.3 km(s)"


def test_nearest_arch_site_is_named_with_its_distance_in_km():
    group = _group(ProximityResult(features=_features(({"BORDENNUMBER": "EkRj-1"}, 3_449.0))))

    status = _build([_task(job_status.ARCH_SITES, "nearest")], [group])

    assert status.nearest_arch_site == "3.4 (km) - EkRj-1"


def test_nothing_within_the_search_distance_says_so():
    tasks = [_task(job_status.INDIAN_RESERVES, "nearest"), _task(job_status.ARCH_SITES, "nearest")]
    groups = [_group(ProximityResult(features=[])), _group(ProximityResult(features=[]))]

    status = _build(tasks, groups)

    assert status.nearest_indian_reserve == "No Indian Reserve within 25km"
    assert status.nearest_arch_site == "No Arch Site within 25km"


def test_a_failed_dataset_reads_failed_not_blank():
    tasks = [_task(job_status.MAPSHEETS), _task(job_status.ALR), _task(job_status.ARCH_SITES, "nearest")]
    groups = [_group(None, failed=True)] * 3

    status = _build(tasks, groups)

    assert status.mapsheets == "FAILED"
    assert status.in_alr == "FAILED"
    assert status.nearest_arch_site == "FAILED"


def test_a_dataset_that_was_not_run_reads_not_checked():
    """No Tab 1 registry was loaded: nothing was looked up, which is not the
    same as nothing being there."""
    status = _build([], [])

    assert status.mapsheets == "Not checked"
    assert status.in_alr == "Not checked"
    assert status.nearest_indian_reserve == "Not checked"


def test_only_the_tab1_registry_feeds_the_tab():
    """The common registry reads some of the same tables, with its own filters."""
    tasks = [_task(job_status.MAPSHEETS, registry="one_status_common_datasets")]

    status = _build(tasks, [_overlay({"MAP_TILE_DISPLAY_NAME": "092P.045"})])

    assert status.mapsheets == "Not checked"


def test_tenure_facts_and_request_details_are_carried_over():
    tenure = TenureFacts(
        applicant_name="ACME GRAVEL LTD.",
        received_dates=("2026-01-15",),
        details={"TENURE_TYPE": ["LICENCE"], "INTRID_SID": ["987654"], "TENURE_AREA_IN_HECTARES": ["12.5"]},
    )

    status = _build(
        [], [],
        run_by="Alice", region="Cariboo", crown_file_number="7410123", disposition_number="55", tenure=tenure,
    )

    assert status.run_by == "Alice" and status.run_date == RUN_DATE
    assert (status.crown_file_number, status.disposition_number, status.region) == ("7410123", "55", "Cariboo")
    assert status.applicant_name == "ACME GRAVEL LTD."
    assert status.received_dates == ("2026-01-15",)
    assert status.tenure_type == ("LICENCE",)
    assert status.parcel_numbers == ("987654",)
    assert status.tenure_area_ha == ("12.5",)
    assert status.tenure_location == ()


def test_an_uploaded_aoi_has_no_file_details():
    status = _build([], [])

    assert status.crown_file_number == "" and status.applicant_name == ""
    assert status.tenure_type == ()


def test_regional_district_and_municipality_are_read_from_the_bcgw_name_column():
    """Both tables name their areas in ADMIN_AREA_NAME. The ArcGIS Pro tool
    asks for REGIONAL_DISTRICT_NAME and MUNICIPALITY_NAME, which BCGW no
    longer has."""
    status = _build(
        [_task(job_status.REGIONAL_DISTRICTS), _task(job_status.MUNICIPALITIES)],
        [_overlay({"ADMIN_AREA_NAME": "Sunshine Coast Regional District"}),
         _overlay({"ADMIN_AREA_NAME": "District of Sechelt"})],
    )

    assert status.regional_districts == ("Sunshine Coast Regional District",)
    assert status.municipalities == ("District of Sechelt",)


def test_the_tab1_registry_only_summarises_columns_its_tables_have():
    """Each dataset in the registry lists the table's columns, as read from
    BCGW when the registry was built. A summary column outside that list is
    never read, and its line on the tab comes out blank - the same as a column
    that is empty, so nothing in a run can tell the two apart. It is caught here."""
    from pathlib import Path

    from ast_engine.config.registry import utils

    registry_path = Path(job_status.__file__).parents[1] / "config" / "registry" / "tab1" / "tab1.yaml"
    registry = utils.load_yaml(registry_path)

    # DISTANCE is not a column: the nearest analysis works it out.
    unknown = {
        dataset.name: sorted(set(dataset.aggregate_columns) - set(dataset.columns) - {"DISTANCE"})
        for dataset in registry.datasets
    }

    assert {name: columns for name, columns in unknown.items() if columns} == {}
