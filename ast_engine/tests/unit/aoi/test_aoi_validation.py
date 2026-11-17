"""AOI orchestration: real builder outputs, child inputs, profiles and error boundaries."""

from unittest.mock import create_autospec

import pytest
from shapely.geometry import MultiPolygon, Point, box

from ast_engine.core.aoi import AOIBuilder
from ast_engine.core.aoi.exceptions import AOIBuildError, AOINormalizationError, AOIValidationError
from ast_engine.core.aoi.validator import AOIValidator
from ast_engine.core.validation.geometry.geometry_validation import (
    GeometryValidationError,
    GeometryValidator,
)
from ast_engine.core.validation.models import ValidationIssue
from ast_engine.core.validation.schema import ValidationProfile
from ast_engine.core.validation.spatial.spatial_validation import (
    SpatialValidationError,
    SpatialValidator,
)
from ast_engine.tests.unit.validation.validation_cases import (
    UNITS,
    build,
    frame,
    geometry_policy,
    layer,
    rule,
)

pytestmark = pytest.mark.unit

@pytest.fixture
def geometry_stub(monkeypatch):
    child = GeometryValidator(
        geometry_policy(rule(threshold_ha=0.1)),
        profile=ValidationProfile.RUNTIME,
    )
    monkeypatch.setattr(child, "validate", create_autospec(child.validate))
    return child


def test_baseline_has_no_hidden_validation_limits():
    result = build(AOIBuilder(), box(0, 0, 1, 1))
    assert result.validation.issues == ()
    assert result.is_valid and not result.has_errors and not result.has_warnings
    assert not result.validation.geometry_checks_run and not result.validation.spatial_checks_run
    assert result.validation.checked_spatial_layers == ()
    assert result.validation.profile == ValidationProfile.RUNTIME


def test_multipart_aoi_collects_both_children_after_a_blocking_geometry_finding():
    geom = GeometryValidator(geometry_policy(rule(rule_id="small_part", threshold_ha=0.02)))
    spatial = SpatialValidator(
        (layer("review", scope="part", rules={"overlap": "warning"}),),
        reference_layers={UNITS: frame(box(18, -1, 32, 11))},
    )
    builder = AOIBuilder(validator=AOIValidator(geometry_validator=geom, spatial_validator=spatial))
    result = build(builder, MultiPolygon([box(0, 0, 10, 10), box(20, 0, 30, 10)]))
    left, right = sorted(result.aoi.parts, key=lambda p: p.geometry.bounds[0])
    assert left.part_id != right.part_id
    assert {i.subject_id for i in result.errors} == {left.part_id, right.part_id}
    assert [f.category for f in result.validation.issues] == ["geometry", "geometry", "spatial"]
    assert all(i.code == "SMALL_PART" and i.is_blocking for i in result.errors)
    (warning,) = result.warnings
    assert (warning.subject_id, warning.layer_name, warning.rule_id) == (
        right.part_id,
        "review",
        "review.overlap",
    )
    assert result.has_errors and not result.is_valid and result.has_warnings
    assert result.validation.geometry_checks_run and result.validation.spatial_checks_run
    assert result.validation.checked_spatial_layers == ("review",)


def test_injected_instance_receives_normalized_parts_and_finding_survives_the_builder(geometry_stub):
    stub = geometry_stub
    issue = ValidationIssue(
        severity=" INFO ",
        code=" custom ",
        message="Review parcel",
        category=" Geometry ",
        scope="footprint",
        subject_id="parcel",
        rule_id="manual",
        tags=[" Review ", "review"],
    )
    stub.validate.return_value = (issue,)
    builder = AOIBuilder(validator=AOIValidator(geometry_validator=stub))
    result = build(builder, MultiPolygon([box(0, 0, 1, 1), box(3, 0, 4, 1)]))
    stub.validate.assert_called_once()
    args = stub.validate.call_args.kwargs
    assert args["footprint_id"] == "parcel"
    assert args["subject_ids"] == tuple(p.part_id for p in result.aoi.parts)
    assert args["gdf"].crs == result.aoi.gdf.crs
    assert all(
        g.equals(p.geometry) for g, p in zip(args["gdf"].geometry, result.aoi.parts, strict=True)
    )
    assert result.validation.issues == result.infos == (issue,) and result.is_valid
    assert result.validation.geometry_checks_run and not result.validation.spatial_checks_run
    assert issue.model_dump(mode="json") == {
        "severity": "info",
        "code": "CUSTOM",
        "message": "Review parcel",
        "layer_name": None,
        "subject_id": "parcel",
        "category": "geometry",
        "scope": "footprint",
        "rule_id": "manual",
        "tags": ["review"],
        "is_blocking": False,
    }


def test_expected_ids_are_forwarded_per_job_and_missing_input_is_a_validation_stage_failure():
    sv = SpatialValidator(
        (layer(id_field="ORG", expected_from="selected", rules={"outside_expected": "error"}),),
        reference_layers={UNITS: frame(box(0, 0, 10, 10), box(10, 0, 20, 10), ORG=["RCB", "RTO"])},
    )
    v = AOIValidator(spatial_validator=sv)
    assert v.required_spatial_parameters == frozenset({"selected"})
    builder, area = AOIBuilder(validator=v), box(1, 1, 2, 2)
    assert build(builder, area, parameters={"selected": ["RCB"]}).is_valid
    blocked = build(builder, area, parameters={"selected": ["RTO"]})
    assert [f.code for f in blocked.errors] == ["SPATIAL_OUTSIDE_EXPECTED"]

    with pytest.raises(AOIBuildError) as caught:
        build(builder, area)
    assert (caught.value.stage, caught.value.aoi_id) == ("validation", "parcel")
    assert isinstance(caught.value.__cause__, AOIValidationError)
    child_error = caught.value.__cause__.__cause__
    assert isinstance(child_error, SpatialValidationError)
    assert "requires nonempty parameter 'selected'" in str(child_error)


def test_parameters_with_spatial_disabled_raise_instead_of_disappearing():
    v = AOIValidator()
    assert v.required_spatial_parameters == frozenset()
    good = build(AOIBuilder(), box(0, 0, 1, 1)).aoi
    with pytest.raises(AOIValidationError, match="spatial validation is disabled") as error:
        v.validate(
            gdf=good.gdf, parts=good.parts, aoi_id=good.aoi_id, parameters={"selected": ["RCB"]}
        )
    assert isinstance(error.value.__cause__, SpatialValidationError)


def test_normalization_rejects_unusable_geometry_before_a_child_is_run(geometry_stub):
    stub = geometry_stub
    builder = AOIBuilder(validator=AOIValidator(geometry_validator=stub))
    with pytest.raises(AOIBuildError) as error:
        build(builder, Point(0, 0))
    assert error.value.stage == "normalization"
    assert isinstance(error.value.__cause__, AOINormalizationError)
    stub.validate.assert_not_called()


def test_child_execution_failure_is_not_converted_to_a_policy_finding(geometry_stub):
    stub = geometry_stub
    failure = GeometryValidationError("unable to measure")
    stub.validate.side_effect = failure
    builder = AOIBuilder(validator=AOIValidator(geometry_validator=stub))
    with pytest.raises(AOIBuildError) as error:
        build(builder, box(0, 0, 10, 10))
    assert error.value.stage == "validation"
    assert isinstance(error.value.__cause__, AOIValidationError)
    assert error.value.__cause__.__cause__ is failure


def test_runtime_reports_no_spatial_checks_when_all_layers_are_submission_only():
    policy = layer(run_in=["submission"])
    spatial = SpatialValidator(
        (policy,), reference_layers={UNITS: frame()}, profile=ValidationProfile.RUNTIME
    )
    result = build(AOIBuilder(validator=AOIValidator(spatial_validator=spatial)), box(0, 0, 5, 5))
    assert result.is_valid and result.validation.checked_spatial_layers == ()
    assert not result.validation.spatial_checks_run
    with pytest.raises(AOIValidationError, match="same profile"):
        AOIValidator(spatial_validator=spatial, profile=ValidationProfile.SUBMISSION)