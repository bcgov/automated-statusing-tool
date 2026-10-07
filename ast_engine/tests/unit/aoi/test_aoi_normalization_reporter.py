from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict

import geopandas as gpd
import pytest

from ast_engine.core.aoi.exceptions import AOINormalizationError, DataCRSError
from ast_engine.core.aoi.models import AOINormalizationReport, AOIRequest
from ast_engine.core.aoi.normalization_reporter import AOINormalizationReportBuilder
from ast_engine.tests.helpers.aoi_geometry import aoi_gdf, rect
from ast_engine.tests.helpers.aoi_requests import make_aoi_request


pytestmark = pytest.mark.unit


def _frame(count: int = 1, *, crs="EPSG:3005") -> gpd.GeoDataFrame:
    """Fresh frames whose row counts and CRS are easy to specify in tests."""
    return aoi_gdf(
        [rect(i * 200, 0, i * 200 + 100, 100) for i in range(count)],
        crs=crs,
    )


def _record_required_steps(
    reporter: AOINormalizationReportBuilder,
    *,
    count: int = 1,
    request: AOIRequest | None = None,
) -> None:
    """Supply a complete simple run for tests focusing on another behavior.

    The missing-event tests call setters explicitly instead of using this helper,
    so these defaults cannot hide a required step that their scenario omits.
    """
    if request is None:
        request = make_aoi_request()
    reporter.set_repair_input_feature_count(count)
    reporter.set_cleaned_feature_count(count)
    reporter.set_policy_input(
        request=request, input_feature_count=count, overlaps_before=False
    )
    reporter.set_policy_output(output_feature_count=count, overlaps_after=False)


# Recording events and constructing the output snapshot


def test_report_records_counts_policy_and_accumulated_cleanup_events():
    source = _frame(6)
    output = _frame(2)
    request = make_aoi_request(
        dissolve_mode="by_fields",
        dissolve_fields=("region", "group_id"),
        allow_overlaps=False,
    )
    reporter = AOINormalizationReportBuilder.from_input_gdf(source)

    # Feed events directly. The reporter does not inspect or clean these rows.
    reporter.add_null_empty_removed(2)
    reporter.set_repair_input_feature_count(4)
    reporter.add_repaired_feature()
    reporter.add_repaired_feature()
    reporter.add_polygon_extraction_counts(
        {
            "input_component_count": 3,
            "polygon_component_count": 2,
            "nonpolygon_component_drop_count": 1,
        }
    )
    reporter.add_polygon_extraction_counts(
        {
            "input_component_count": 4,
            "polygon_component_count": 3,
            "nonpolygon_component_drop_count": 1,
        }
    )
    reporter.add_null_empty_removed(1)
    reporter.set_cleaned_feature_count(3)
    reporter.set_policy_input(
        request=request, input_feature_count=3, overlaps_before=True
    )
    reporter.set_policy_output(output_feature_count=2, overlaps_after=False)
    reporter.add_note("Recorded cleanup events.")

    report = reporter.build(output)

    assert isinstance(report, AOINormalizationReport)
    assert asdict(report) == {
        "input_feature_count": 6,
        "cleaned_feature_count": 3,
        "output_feature_count": 2,
        "input_crs": "EPSG:3005",
        "output_crs": "EPSG:3005",
        "null_or_empty_removed_count": 3,
        "repair_input_feature_count": 4,
        "repaired_feature_count": 2,
        "polygon_extract_input_feature_count": 7,
        "polygon_extract_output_feature_count": 5,
        "polygon_extract_drop_count": 2,
        "policy_name": "by_fields",
        "dissolve_fields_used": ("region", "group_id"),
        "allow_overlaps": False,
        "policy_applied": True,
        "policy_input_feature_count": 3,
        "policy_output_feature_count": 2,
        "overlaps_detected_before_policy": True,
        "overlaps_present_after_policy": False,
        "overlaps_resolved_by_policy": True,
        "was_reprojected": False,
        "notes": ("Recorded cleanup events.",),
    }


def test_zero_counts_false_flags_and_empty_tuples_are_valid_recorded_values():
    source = _frame(0)
    reporter = AOINormalizationReportBuilder(source)
    _record_required_steps(reporter, count=0)

    report = reporter.build(_frame(0))

    assert report.input_feature_count == 0
    assert report.cleaned_feature_count == 0
    assert report.output_feature_count == 0
    assert report.repair_input_feature_count == 0
    assert report.null_or_empty_removed_count == 0
    assert report.repaired_feature_count == 0
    assert report.polygon_extract_input_feature_count == 0
    assert report.polygon_extract_output_feature_count == 0
    assert report.polygon_extract_drop_count == 0
    assert report.policy_input_feature_count == 0
    assert report.policy_output_feature_count == 0
    assert report.allow_overlaps is False
    assert report.overlaps_detected_before_policy is False
    assert report.overlaps_present_after_policy is False
    assert report.overlaps_resolved_by_policy is False
    assert report.was_reprojected is False
    assert report.dissolve_fields_used == ()
    assert report.notes == ()


@pytest.mark.parametrize(
    ("mode", "fields", "allow_overlaps"),
    [
        pytest.param("full_union", (), False, id="full-union"),
        pytest.param("preserve_features", (), True, id="preserve-features"),
        pytest.param(
            "by_fields", ("region", "group_id"), False, id="by-multiple-fields"
        ),
    ],
)
def test_policy_metadata_is_taken_from_the_supplied_request(mode, fields, allow_overlaps):
    source = _frame()
    request = make_aoi_request(
        dissolve_mode=mode,
        dissolve_fields=fields,
        allow_overlaps=allow_overlaps,
    )
    reporter = AOINormalizationReportBuilder(source)
    _record_required_steps(reporter, request=request)

    report = reporter.build(source)

    assert report.policy_name == mode
    assert report.dissolve_fields_used == fields
    assert isinstance(report.dissolve_fields_used, tuple)
    assert report.allow_overlaps is allow_overlaps
    # This means the policy step was recorded, including preserve_features.
    assert report.policy_applied is True


@pytest.mark.parametrize(
    ("before", "after", "expected_resolved"),
    [
        pytest.param(False, False, False, id="none-before-or-after"),
        pytest.param(False, True, False, id="introduced-overlap"),
        pytest.param(True, False, True, id="overlaps-resolved"),
        pytest.param(True, True, False, id="overlaps-remain"),
    ],
)
def test_overlap_resolution_requires_overlaps_before_and_none_after(
    before, after, expected_resolved
):
    source = _frame()
    reporter = AOINormalizationReportBuilder(source)
    reporter.set_repair_input_feature_count(1)
    reporter.set_cleaned_feature_count(1)
    reporter.set_policy_input(
        request=make_aoi_request(allow_overlaps=True),
        input_feature_count=1,
        overlaps_before=before,
    )
    reporter.set_policy_output(output_feature_count=1, overlaps_after=after)

    report = reporter.build(source)

    assert report.overlaps_detected_before_policy is before
    assert report.overlaps_present_after_policy is after
    assert report.overlaps_resolved_by_policy is expected_resolved
    assert reporter.overlaps_present_after_policy is after


# Required steps and missing CRS


@pytest.mark.parametrize(
    ("missing_step", "expected_field"),
    [
        pytest.param("repair", "repair_input_feature_count", id="repair-input"),
        pytest.param("cleaned", "cleaned_feature_count", id="cleaned-count"),
        pytest.param("policy", "policy_name", id="policy-not-recorded"),
        pytest.param("policy_output", "policy_output_feature_count", id="policy-output"),
    ],
)
def test_build_rejects_a_run_with_a_required_step_missing(missing_step, expected_field):
    source = _frame()
    reporter = AOINormalizationReportBuilder(source)

    if missing_step != "repair":
        reporter.set_repair_input_feature_count(1)
    if missing_step != "cleaned":
        reporter.set_cleaned_feature_count(1)
    if missing_step != "policy":
        reporter.set_policy_input(
            request=make_aoi_request(), input_feature_count=1, overlaps_before=False
        )
        if missing_step != "policy_output":
            reporter.set_policy_output(output_feature_count=1, overlaps_after=False)

    with pytest.raises(AOINormalizationError, match=expected_field):
        reporter.build(source)


def test_policy_output_cannot_be_recorded_before_policy_input():
    reporter = AOINormalizationReportBuilder(_frame())

    with pytest.raises(AOINormalizationError, match="overlaps_detected_before_policy"):
        reporter.set_policy_output(output_feature_count=1, overlaps_after=False)


def test_overlap_property_cannot_be_read_before_policy_output_is_recorded():
    reporter = AOINormalizationReportBuilder(_frame())
    reporter.set_policy_input(
        request=make_aoi_request(), input_feature_count=1, overlaps_before=False
    )

    with pytest.raises(AOINormalizationError, match="overlaps_present_after_policy"):
        _ = reporter.overlaps_present_after_policy


def test_missing_input_crs_cannot_produce_a_complete_report():
    reporter = AOINormalizationReportBuilder(_frame(crs=None))
    _record_required_steps(reporter)

    with pytest.raises(AOINormalizationError, match="input_crs"):
        reporter.build(_frame(crs="EPSG:3005"))


def test_missing_output_crs_raises_a_crs_error():
    reporter = AOINormalizationReportBuilder(_frame())
    _record_required_steps(reporter)

    with pytest.raises(DataCRSError, match="output CRS"):
        reporter.build(_frame(crs=None))


# CRS events, note order, snapshots, and independent instances


def test_reprojection_event_sets_the_flag_and_preserves_note_order():
    source = aoi_gdf([rect(-124, 49, -123, 50)], crs="EPSG:4326")
    output = _frame(crs="EPSG:3005")
    reporter = AOINormalizationReportBuilder(source)
    _record_required_steps(reporter)
    reporter.add_note("Before reprojection.")
    reporter.mark_reprojected(from_crs="EPSG:4326", to_crs="EPSG:3005")
    reporter.add_note("After reprojection.")

    report = reporter.build(output)

    assert report.input_crs == "EPSG:4326"
    assert report.output_crs == "EPSG:3005"
    assert report.was_reprojected is True
    assert len(report.notes) == 3
    assert report.notes[0] == "Before reprojection."
    assert "EPSG:4326" in report.notes[1]
    assert "EPSG:3005" in report.notes[1]
    assert report.notes[2] == "After reprojection."


def test_built_reports_remain_immutable_when_more_events_are_recorded():
    source = _frame()
    reporter = AOINormalizationReportBuilder(source)
    _record_required_steps(reporter)
    reporter.add_note("First note.")

    first = reporter.build(source)
    reporter.add_note("Second note.")
    reporter.add_repaired_feature()
    second = reporter.build(source)

    assert first.notes == ("First note.",)
    assert first.repaired_feature_count == 0
    assert second.notes == ("First note.", "Second note.")
    assert second.repaired_feature_count == 1
    assert isinstance(first.notes, tuple)
    assert isinstance(second.notes, tuple)
    with pytest.raises(FrozenInstanceError):
        first.cleaned_feature_count = 99


def test_reporter_instances_do_not_share_notes_or_counters():
    first = AOINormalizationReportBuilder(_frame())
    second = AOINormalizationReportBuilder(_frame())
    _record_required_steps(first)
    _record_required_steps(second)

    first.add_note("Only the first reporter recorded this.")
    first.add_repaired_feature()

    first_report = first.build(_frame())
    second_report = second.build(_frame())

    assert first_report.notes == ("Only the first reporter recorded this.",)
    assert first_report.repaired_feature_count == 1
    assert second_report.notes == ()
    assert second_report.repaired_feature_count == 0


def test_input_metadata_is_captured_at_construction_and_output_metadata_at_build():
    source = _frame(2, crs="EPSG:3005")
    reporter = AOINormalizationReportBuilder.from_input_gdf(source)

    # Alter the same frame after construction to prove input metadata is a
    # snapshot. CRS reassignment here tests bookkeeping; it is not reprojection.
    source.drop(index=source.index[-1], inplace=True)
    source.set_crs("EPSG:26910", allow_override=True, inplace=True)
    reporter.add_null_empty_removed(1)
    _record_required_steps(reporter, count=1)

    report = reporter.build(source)

    assert report.input_feature_count == 2
    assert report.input_crs == "EPSG:3005"
    assert report.cleaned_feature_count == 1
    assert report.output_feature_count == 1
    assert report.output_crs == "EPSG:26910"
    assert report.null_or_empty_removed_count == 1
