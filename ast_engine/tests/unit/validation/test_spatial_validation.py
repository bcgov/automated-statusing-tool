"""Spatial predicates, per-request ID binding, reference preparation and profiles."""

import pytest
from pydantic import ValidationError
from shapely.geometry import Point, box

from ast_engine.core.exceptions import DataCRSError, SpatialGeometryError
from ast_engine.core.validation.schema import ValidationProfile
from ast_engine.core.validation.spatial.spatial_validation import (
    SpatialValidationError,
    SpatialValidator,
)
from ast_engine.tests.unit.validation.validation_cases import UNITS, frame, layer

pytestmark = pytest.mark.unit


def validator_for(policy, source):
    return SpatialValidator(
        (policy,), reference_layers={UNITS: source}, profile=ValidationProfile.RUNTIME
    )


@pytest.mark.parametrize(
    "geom,rule_id",
    [
        (box(2, 2, 4, 4), "SPATIAL_OVERLAP"),  # contained
        (box(-5, -5, 15, 15), "SPATIAL_OVERLAP"),  # contains the reference
        (box(10, 2, 12, 4), "SPATIAL_NO_OVERLAP"),  # shared edge
        (box(10, 10, 12, 12), "SPATIAL_NO_OVERLAP"),  # shared point
        (box(20, 20, 22, 22), "SPATIAL_NO_OVERLAP"),  # disjoint
    ],
)
def test_overlap_means_positive_area(geom, rule_id):
    policy = layer(rules={"overlap": "error", "no_overlap": "info"})
    validator = validator_for(policy, frame(box(0, 0, 10, 10)))
    (finding,) = validator.validate(gdf=frame(geom), footprint_id="parcel")
    assert (
        finding.rule_id,
        finding.category,
        finding.layer_name,
        finding.subject_id,
        finding.scope,
    ) == (
        rule_id,
        "spatial",
        "units",
        "parcel",
        "footprint",
    )
    assert finding.code == ("units.overlap".upper() if rule_id == "SPATIAL_OVERLAP" else "units.no_overlap".upper())
    assert finding.is_blocking == (rule_id == "SPATIAL_OVERLAP")


@pytest.mark.parametrize(
    "geom,expected",
    [
        (box(9, 0, 11, 1), ["SPATIAL_NO_OVERLAP"]),  # 1 m² inside equals tolerance
        (box(8, 0, 11, 1), []),  # 2 inside, 1 outside equals tolerance
        (box(8, 0, 12, 1), ["SPATIAL_PARTIALLY_OUTSIDE"]),
    ],
)
def test_inside_and_outside_tolerances_use_strict_comparisons(geom, expected):
    policy = layer(
        area_tolerance_m2=1.0, rules={"no_overlap": "error", "partial_outside": "warning"}
    )
    found = validator_for(policy, frame(box(0, 0, 10, 10))).validate(gdf=frame(geom))
    assert [f.rule_id for f in found] == expected


def test_ids_are_trimmed_and_dissolved_once_and_selections_are_per_request():
    src = frame(
        box(0, 0, 5, 10), box(5, 0, 10, 10), box(10, 0, 20, 10), ORG=[" RCB ", "RCB", "RTO"]
    )
    policy = layer(
        id_field="ORG",
        expected_from="selected",
        rules={"multiple_units": "warning", "outside_expected": "error"},
    )
    validator = validator_for(policy, src)
    # Mutate the actual input to preparation, not a fake reader's upstream copy.
    src.loc[0, "geometry"] = box(100, 100, 105, 110)
    src.loc[1, "ORG"] = "changed"
    a = frame(box(1, 1, 9, 9))  # spans two original features of the same logical unit
    for selected, rule_id in [
        ([" RCB "], []),
        (["RTO"], ["SPATIAL_OUTSIDE_EXPECTED"]),
        (["RCB"], []),
    ]:
        found = validator.validate(gdf=a, parameters={"selected": selected})
        assert [f.rule_id for f in found] == rule_id
    both = validator.validate(gdf=frame(box(8, 1, 12, 9)), parameters={"selected": ["RCB", "RTO"]})
    assert [f.rule_id for f in both] == ["SPATIAL_MULTIPLE_UNITS"]
    assert policy.expected_from == "selected" and policy.expected_ids == ()


@pytest.mark.parametrize(
    "parameters,match",
    [
        (None, "requires nonempty parameter"),
        ({"selected": []}, "requires nonempty parameter"),
        ({"surprise": ["A"]}, "Unknown validation parameters"),
        ({"selected": ["missing"]}, "Unknown expected IDs"),
        ({"selected": [" A ", "A"]}, "duplicates"),
        ({"selected": [True]}, "booleans"),
        ({"selected": "A"}, "list or tuple"),
    ],
)
def test_bad_request_selection_is_an_execution_error(parameters, match):
    val = validator_for(
        layer(id_field="ID", expected_from="selected", rules={"outside_expected": "error"}),
        frame(box(0, 0, 5, 5), ID=["A"]),
    )
    with pytest.raises(SpatialValidationError, match=match):
        val.validate(gdf=frame(box(1, 1, 2, 2)), parameters=parameters)


def test_static_expected_ids_validate_at_preparation():
    policy = layer(id_field="UNIT", expected_ids=[7], rules={"outside_expected": "error"})
    val = validator_for(policy, frame(box(0, 0, 10, 10), UNIT=[7]))
    assert val.required_parameters == frozenset()
    assert val.validate(gdf=frame(box(0, 0, 1, 1))) == ()
    with pytest.raises(SpatialValidationError, match="Unknown expected IDs"):
        validator_for(policy, frame(box(0, 0, 10, 10), UNIT=["7"]))


def test_part_scope_reports_only_the_offending_part_and_footprint_scope_reports_once():
    ref = frame(box(0, 0, 10, 10))
    rows = frame(box(1, 1, 2, 2), box(20, 1, 21, 2))
    val = SpatialValidator(
        (layer("parts", scope="part"), layer("whole", rules={"partial_outside": "warning"})),
        reference_layers={UNITS: ref},
    )
    found = val.validate(gdf=rows, subject_ids=("west", "east"), footprint_id="P")
    assert [(f.rule_id, f.subject_id) for f in found] == [
        ("SPATIAL_NO_OVERLAP", "east"),
        ("SPATIAL_PARTIALLY_OUTSIDE", "P"),
    ]
    with pytest.raises(SpatialValidationError, match="require subject_ids"):
        val.validate(gdf=rows)


def test_only_active_layers_require_selections_but_known_inactive_key_is_accepted():
    runtime_layer = layer("province")
    submission_layer = layer(
        "selected",
        run_in=["submission"],
        id_field="UNIT",
        expected_from="front_end_selection",
        rules={"outside_expected": "error"},
    )
    cache = {UNITS: frame(box(0, 0, 8, 8), UNIT=["A"])}
    runtime = SpatialValidator(
        (runtime_layer, submission_layer), reference_layers=cache, profile=ValidationProfile.RUNTIME
    )
    submission = SpatialValidator(
        (runtime_layer, submission_layer),
        reference_layers=cache,
        profile=ValidationProfile.SUBMISSION,
    )
    rows = frame(box(1, 1, 2, 2))
    assert runtime.required_parameters == frozenset()
    assert submission.required_parameters == frozenset({"front_end_selection"})
    assert runtime.validate(gdf=rows) == ()
    assert runtime.validate(gdf=rows, parameters={"front_end_selection": ["A"]}) == ()
    with pytest.raises(SpatialValidationError, match="front_end_selection"):
        submission.validate(gdf=rows)


def test_empty_source_means_no_overlap_missing_source_is_an_error():
    val = validator_for(layer(), frame())
    (finding,) = val.validate(gdf=frame(box(0, 0, 1, 1)))
    assert finding.rule_id == "SPATIAL_NO_OVERLAP"
    with pytest.raises(SpatialValidationError, match="not cached"):
        SpatialValidator((layer(),), reference_layers={})


def test_reference_in_degrees_is_reprojected_before_intersection():
    src = frame(box(-123.1, 49.1, -123.0, 49.2), crs="EPSG:4326")
    subject = frame(box(-123.08, 49.12, -123.03, 49.17), crs="EPSG:4326").to_crs(3005)
    (finding,) = validator_for(layer(rules={"overlap": "info"}), src).validate(gdf=subject)
    assert finding.rule_id == "SPATIAL_OVERLAP" and src.crs.to_epsg() == 4326


def test_subject_crs_must_match_cache_even_if_both_are_in_metres():
    val = validator_for(layer(), frame(box(0, 0, 1, 1)))
    with pytest.raises(SpatialValidationError, match="differs"):
        val.validate(gdf=frame(box(0, 0, 1, 1), crs="EPSG:26910"))


def test_bad_subject_geometry_is_wrapped_as_a_spatial_execution_error():
    val = validator_for(layer(), frame(box(0, 0, 1, 1)))
    with pytest.raises(SpatialValidationError) as error:
        val.validate(gdf=frame(Point(0, 0)))
    assert isinstance(error.value.__cause__, SpatialGeometryError)


def test_reference_without_crs_raises_spatial_execution_error_with_layer_name():
    with pytest.raises(SpatialValidationError, match="units") as error:
        validator_for(layer(), frame(crs=None))
    cause = error.value.__cause__
    # Startup may add reference context around an already-wrapped frame error.
    if isinstance(cause, SpatialValidationError):
        cause = cause.__cause__
    assert isinstance(cause, DataCRSError)


@pytest.mark.parametrize("scope", ["all_parts", "feature"])
def test_spatial_schema_only_allows_implemented_scopes(scope):
    with pytest.raises(ValidationError) as error:
        layer(scope=scope)
    assert error.value.errors()[0]["loc"] == ("scope",)


@pytest.mark.parametrize("ids", [[True], [1.5], [""], [" A ", "A"], "A"])
def test_invalid_static_expected_ids_are_rejected_for_the_right_field(ids):
    with pytest.raises(ValidationError) as caught:
        layer(id_field="UNIT", expected_ids=ids, rules={"outside_expected": "error"})
    assert caught.value.errors()[0]["loc"] == ("expected_ids",)


@pytest.mark.parametrize(
    "options,reason",
    [
        ({"rules": {}}, "enable at least one"),
        ({"rules": {"multiple_units": "error"}}, "require id_field"),
        ({"id_field": "ID", "rules": {"outside_expected": "error"}}, "requires expected_ids"),
        (
            {
                "id_field": "ID",
                "expected_from": "selected",
                "expected_ids": ["A"],
                "rules": {"outside_expected": "error"},
            },
            "not both",
        ),
        ({"expected_ids": ["A"], "rules": {"no_overlap": "info"}}, "require outside_expected"),
    ],
)
def test_spatial_policy_prerequisites_are_checked_at_load(options, reason):
    with pytest.raises(ValidationError, match=reason):
        layer(**options)