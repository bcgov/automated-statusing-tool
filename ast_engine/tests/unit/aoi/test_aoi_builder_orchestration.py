from __future__ import annotations

from dataclasses import dataclass, replace
from unittest.mock import Mock, create_autospec

import pytest

import ast_engine.core.aoi.aoi_builder as builder_module
from ast_engine.core.aoi.aoi_builder import AOIBuilder
from ast_engine.core.aoi.exceptions import (
    AOIBuildError,
    AOIInspectionError,
    AOINormalizationError,
    AOIPartBuildError,
    AOIValidationError,
    SpatialGeometryError,
)
from ast_engine.core.aoi.inspector import AOIInspector
from ast_engine.core.aoi.models import (
    AOIBuildRequest,
    AOIBuildResult,
    AOINormalizationReport,
    AOIPart,
    AOIProperties,
    AOIValidationResult,
    AreaOfInterest,
    NormalizedAOI,
    ValidationIssue,
)
from ast_engine.core.aoi.normalizer import AOINormalizer
from ast_engine.core.aoi.parts_builder import AOIPartBuilder
from ast_engine.core.aoi.validator import AOIValidator
from ast_engine.tests.helpers.aoi_geometry import aoi_gdf, rect
from ast_engine.tests.helpers.aoi_requests import build_aoi_request, make_aoi_request


pytestmark = pytest.mark.unit

STAGE_ORDER = ("normalization", "part_building", "inspection", "validation")

DEPENDENCY_TYPES = {
    "normalizer": AOINormalizer,
    "part_builder": AOIPartBuilder,
    "inspector": AOIInspector,
    "validator": AOIValidator,
}


@dataclass
class _BuilderCase:
    """Keep one test's related inputs together; no shared mutable test data."""

    builder: AOIBuilder
    request: AOIBuildRequest
    normalized: NormalizedAOI
    parts: tuple[AOIPart, ...]
    properties: AOIProperties
    validation: AOIValidationResult
    stages: dict[str, Mock]
    trace: Mock


@pytest.fixture
def builder_case() -> _BuilderCase:
    # Raw and normalized data deliberately differ in row count and column name.
    # A builder that accidentally forwards the raw frame downstream must fail.
    raw = aoi_gdf(
        [rect(0, 0, 100, 100), rect(100, 0, 200, 100)],
        SourceId=["A", "B"],
    ).rename_geometry("raw_shape")
    spec = make_aoi_request(
        aoi_id="watershed_17",
        name="Watershed 17",
        dissolve_mode="full_union",
        allow_overlaps=False,
    )
    request = build_aoi_request(spec=spec, raw_gdf=raw)

    normalized_gdf = aoi_gdf([rect(0, 0, 200, 100)]).rename_geometry("shape")
    report = AOINormalizationReport(
        input_feature_count=2,
        cleaned_feature_count=2,
        output_feature_count=1,
        input_crs="EPSG:3005",
        output_crs="EPSG:3005",
        null_or_empty_removed_count=0,
        repair_input_feature_count=0,
        repaired_feature_count=0,
        polygon_extract_input_feature_count=2,
        polygon_extract_output_feature_count=2,
        polygon_extract_drop_count=0,
        policy_name="full_union",
        dissolve_fields_used=(),
        allow_overlaps=False,
        policy_applied=True,
        policy_input_feature_count=2,
        policy_output_feature_count=1,
        overlaps_detected_before_policy=False,
        overlaps_present_after_policy=False,
        overlaps_resolved_by_policy=False,
        was_reprojected=False,
        notes=("Controlled normalization output for builder tests.",),
    )
    normalized = NormalizedAOI(gdf=normalized_gdf, report=report)

    # Explicit cached metadata: no AOIPart.from_gdf() or part-builder setup.
    parts = (
        AOIPart(
            part_id="watershed_17_part_0001",
            parent_aoi_id=spec.aoi_id,
            geom_type="Polygon",
            part_index=1,
            gdf=normalized_gdf.copy(deep=True),
            bounds=(0.0, 0.0, 200.0, 100.0),
            area_ha=2.0,
            vertex_count=5,
            has_z=False,
            has_m=False,
        ),
    )
    properties = AOIProperties(
        crs_epsg=3005,
        crs_string="EPSG:3005",
        footprint_area_ha=2.0,
        bounds=(0.0, 0.0, 200.0, 100.0),
        part_count=1,
        parts_area_ha=2.0,
        feature_count=1,
        geometry_type="Polygon",
        parts_to_footprint_ratio=1.0,
        vertex_count=5,
        max_vertices_per_part=5,
        has_z=False,
        has_m=False,
    )
    validation = AOIValidationResult(issues=())

    dependencies = {
        name: create_autospec(stage_type, instance=True, spec_set=True)
        for name, stage_type in DEPENDENCY_TYPES.items()
    }
    stages = {
        "normalization": dependencies["normalizer"].normalize_aoi,
        "part_building": dependencies["part_builder"].build_parts,
        "inspection": dependencies["inspector"].inspect,
        "validation": dependencies["validator"].validate,
    }
    stages["normalization"].return_value = normalized
    stages["part_building"].return_value = parts
    stages["inspection"].return_value = properties
    stages["validation"].return_value = validation

    trace = Mock()
    for stage_name, method in stages.items():
        trace.attach_mock(method, stage_name)

    return _BuilderCase(
        builder=AOIBuilder(**dependencies),
        request=request,
        normalized=normalized,
        parts=parts,
        properties=properties,
        validation=validation,
        stages=stages,
        trace=trace,
    )


def _assert_stopped_at(case: _BuilderCase, failed_stage: str) -> None:
    """Earlier stages and the failing stage run once; no later stage runs."""
    expected_calls = list(STAGE_ORDER[: STAGE_ORDER.index(failed_stage) + 1])
    assert [entry[0] for entry in case.trace.mock_calls] == expected_calls


# Successful orchestration and validation outcomes


def test_builder_passes_stage_outputs_forward_and_assembles_the_result(builder_case):
    case = builder_case

    result = case.builder.build_from_request(case.request)

    assert [entry[0] for entry in case.trace.mock_calls] == list(STAGE_ORDER)

    # Check the actual handoffs. Identity checks avoid ambiguous DataFrame ==
    # comparisons and ensure the exact stage output is being forwarded.
    normalize = case.stages["normalization"]
    normalize.assert_called_once()
    args = normalize.call_args.kwargs
    assert set(args) == {"gdf", "request"}
    assert args["gdf"] is case.request.raw_gdf
    assert args["request"] is case.request.spec

    build_parts = case.stages["part_building"]
    build_parts.assert_called_once()
    args = build_parts.call_args.kwargs
    assert set(args) == {"aoi_id", "gdf"}
    assert args["aoi_id"] == case.request.spec.aoi_id
    assert args["gdf"] is case.normalized.gdf

    inspect = case.stages["inspection"]
    inspect.assert_called_once()
    args = inspect.call_args.kwargs
    assert set(args) == {"gdf", "parts"}
    assert args["gdf"] is case.normalized.gdf
    assert args["parts"] is case.parts

    validate = case.stages["validation"]
    validate.assert_called_once()
    args = validate.call_args.kwargs
    assert set(args) == {"gdf", "report", "parts", "properties"}
    assert args["gdf"] is case.normalized.gdf
    assert args["report"] is case.normalized.report
    assert args["parts"] is case.parts
    assert args["properties"] is case.properties

    # The real output objects should expose the supplied request identity and
    # the outputs from the stages, including the complete normalization report.
    assert isinstance(result, AOIBuildResult)
    assert isinstance(result.aoi, AreaOfInterest)
    assert result.aoi.aoi_id == "watershed_17"
    assert result.aoi.name == "Watershed 17"
    assert result.aoi.gdf is case.normalized.gdf
    assert result.aoi.properties is case.properties
    assert result.aoi.parts is case.parts
    assert result.validation is case.validation
    assert result.normalization_report is case.normalized.report
    assert result.is_valid is True


@pytest.mark.parametrize(
    ("severities", "expected_valid"),
    [
        pytest.param(("warning",), True, id="warning-only"),
        pytest.param(("info",), True, id="info-only"),
        pytest.param(("error",), False, id="validation-errors"),
        pytest.param(("error", "warning", "info"), False, id="mixed-issues"),
    ],
)
def test_validation_issues_return_a_complete_result_without_raising(
    builder_case, severities, expected_valid
):
    """A completed validation result with issues is a valid builder outcome.

    These controlled issues avoid depending on actual size thresholds or other
    validator rules, which are tested in the validator's own suite.
    """
    case = builder_case
    validation = AOIValidationResult(
        issues=tuple(
            ValidationIssue(
                severity=severity,
                code=f"TEST_{severity.upper()}",
                message=f"Controlled {severity} finding.",
            )
            for severity in severities
        )
    )
    case.stages["validation"].return_value = validation

    result = case.builder.build_from_request(case.request)

    assert isinstance(result, AOIBuildResult)
    assert result.validation is validation
    assert result.is_valid is expected_valid
    assert result.aoi.gdf is case.normalized.gdf
    assert result.aoi.parts is case.parts
    assert result.aoi.properties is case.properties
    assert result.normalization_report is case.normalized.report
    assert [entry[0] for entry in case.trace.mock_calls] == list(STAGE_ORDER)


# Raised failures, stage context, and stopping the pipeline


@pytest.mark.parametrize(
    ("stage", "stage_error_type"),
    [
        pytest.param("normalization", AOINormalizationError, id="normalization"),
        pytest.param("part_building", AOIPartBuildError, id="part-building"),
        pytest.param("inspection", AOIInspectionError, id="inspection"),
        pytest.param("validation", AOIValidationError, id="validation"),
    ],
)
def test_stage_domain_errors_get_build_context_and_keep_their_cause_chain(
    builder_case, stage, stage_error_type
):
    case = builder_case
    root = SpatialGeometryError("Controlled lower-level geometry failure.")
    failure = stage_error_type("Controlled stage failure.")
    # Simulate a stage error that already wraps a lower-level domain error.
    failure.__cause__ = root
    case.stages[stage].side_effect = failure

    with pytest.raises(AOIBuildError) as exc_info:
        case.builder.build_from_request(case.request)

    error = exc_info.value
    assert error.stage == stage
    assert error.aoi_id == case.request.spec.aoi_id
    assert error.__cause__ is failure
    assert error.__cause__.__cause__ is root
    _assert_stopped_at(case, stage)


@pytest.mark.parametrize("stage", STAGE_ORDER)
def test_unexpected_stage_errors_get_build_context_and_stop_later_stages(
    builder_case, stage
):
    """The outer builder wraps unexpected stage errors for its caller.

    This differs from an individual stage such as the inspector: that stage
    lets unexpected errors reach the builder, which adds stage/AOI context.
    """
    case = builder_case
    failure = RuntimeError("Controlled unexpected failure.")
    case.stages[stage].side_effect = failure

    with pytest.raises(AOIBuildError) as exc_info:
        case.builder.build_from_request(case.request)

    error = exc_info.value
    assert error.stage == stage
    assert error.aoi_id == case.request.spec.aoi_id
    assert error.__cause__ is failure
    _assert_stopped_at(case, stage)


@pytest.mark.parametrize("stage", STAGE_ORDER)
def test_existing_build_errors_pass_through_unchanged_and_stop_later_stages(
    builder_case, stage
):
    case = builder_case
    failure = AOIBuildError(
        "An existing build error from a dependency.",
        stage="inner_stage",
        aoi_id="inner_aoi",
    )
    root = RuntimeError("Original inner failure.")
    failure.__cause__ = root
    case.stages[stage].side_effect = failure

    with pytest.raises(AOIBuildError) as exc_info:
        case.builder.build_from_request(case.request)

    assert exc_info.value is failure
    assert exc_info.value.stage == "inner_stage"
    assert exc_info.value.aoi_id == "inner_aoi"
    assert exc_info.value.__cause__ is root
    _assert_stopped_at(case, stage)


# Builder reuse and constructor injection


def test_reusing_a_builder_does_not_mix_results_from_different_requests(builder_case):
    case = builder_case
    first = case.builder.build_from_request(case.request)

    second_raw = aoi_gdf([rect(1000, 1000, 1200, 1300)])
    second_request = build_aoi_request(
        spec=make_aoi_request(aoi_id="second_aoi", name="Second AOI"),
        raw_gdf=second_raw,
    )
    second_normalized = NormalizedAOI(
        gdf=second_raw.rename_geometry("shape"),
        report=replace(
            case.normalized.report,
            input_feature_count=1,
            cleaned_feature_count=1,
            polygon_extract_input_feature_count=1,
            polygon_extract_output_feature_count=1,
            policy_input_feature_count=1,
            notes=("Normalization report for the second AOI.",),
        ),
    )
    second_parts = (
        replace(
            case.parts[0],
            part_id="second_aoi_part_0001",
            parent_aoi_id="second_aoi",
            gdf=second_normalized.gdf.copy(deep=True),
            bounds=(1000.0, 1000.0, 1200.0, 1300.0),
            area_ha=6.0,
        ),
    )
    second_properties = replace(
        case.properties,
        bounds=(1000.0, 1000.0, 1200.0, 1300.0),
        footprint_area_ha=6.0,
        parts_area_ha=6.0,
    )
    second_validation = AOIValidationResult(issues=())
    case.stages["normalization"].return_value = second_normalized
    case.stages["part_building"].return_value = second_parts
    case.stages["inspection"].return_value = second_properties
    case.stages["validation"].return_value = second_validation

    second = case.builder.build_from_request(second_request)

    assert second.aoi.aoi_id == "second_aoi"
    assert second.aoi.name == "Second AOI"
    assert second.aoi.gdf is second_normalized.gdf
    assert second.aoi.parts is second_parts
    assert second.aoi.properties is second_properties
    assert second.validation is second_validation
    assert second.normalization_report is second_normalized.report

    assert first.aoi.aoi_id == "watershed_17"
    assert first.aoi.gdf is case.normalized.gdf
    assert first.aoi.parts is case.parts
    assert first.aoi.properties is case.properties
    assert first.validation is case.validation
    assert first.normalization_report is case.normalized.report
    assert [entry[0] for entry in case.trace.mock_calls] == list(STAGE_ORDER) * 2

    # The recorded arguments now describe the second call of each stage.
    args = case.stages["normalization"].call_args.kwargs
    assert args["gdf"] is second_request.raw_gdf
    assert args["request"] is second_request.spec
    args = case.stages["part_building"].call_args.kwargs
    assert args["gdf"] is second_normalized.gdf
    assert args["aoi_id"] == "second_aoi"
    args = case.stages["inspection"].call_args.kwargs
    assert args["gdf"] is second_normalized.gdf
    assert args["parts"] is second_parts
    args = case.stages["validation"].call_args.kwargs
    assert args["gdf"] is second_normalized.gdf
    assert args["report"] is second_normalized.report
    assert args["parts"] is second_parts
    assert args["properties"] is second_properties


@pytest.mark.parametrize("missing_dependency", tuple(DEPENDENCY_TYPES))
def test_constructor_creates_only_the_dependency_supplied_as_none(
    builder_case, monkeypatch, missing_dependency
):
    dependencies = {
        name: getattr(builder_case.builder, name) for name in DEPENDENCY_TYPES
    }
    factories = {}
    for name, stage_type in DEPENDENCY_TYPES.items():
        factory = Mock(return_value=create_autospec(stage_type, instance=True))
        # Patch where the builder looks up the constructor it imported.
        monkeypatch.setattr(builder_module, stage_type.__name__, factory)
        factories[name] = factory

    dependencies[missing_dependency] = None

    builder = AOIBuilder(**dependencies)

    for name, factory in factories.items():
        if name == missing_dependency:
            factory.assert_called_once_with()
            assert getattr(builder, name) is factory.return_value
        else:
            factory.assert_not_called()
            assert getattr(builder, name) is dependencies[name]


class _FalseyDependency(Mock):
    """A supplied dependency may evaluate to False and still be a real object."""

    def __bool__(self):
        return False


def test_constructor_keeps_explicit_dependencies_even_when_they_are_falsey(monkeypatch):
    dependencies = {
        name: _FalseyDependency(spec_set=stage_type)
        for name, stage_type in DEPENDENCY_TYPES.items()
    }
    factories = {}
    for name, stage_type in DEPENDENCY_TYPES.items():
        factory = Mock()
        monkeypatch.setattr(builder_module, stage_type.__name__, factory)
        factories[name] = factory

    builder = AOIBuilder(**dependencies)

    for name, dependency in dependencies.items():
        assert bool(dependency) is False
        assert getattr(builder, name) is dependency
        factories[name].assert_not_called()
