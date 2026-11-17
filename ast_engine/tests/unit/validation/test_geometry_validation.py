"""Geometry rules measured on real polygons in metres; hectares are derived from m²."""

import pytest
from pydantic import ValidationError
from shapely.geometry import Polygon, box

from ast_engine.core.exceptions import DataCRSError, SpatialDataError, SpatialGeometryError
from ast_engine.core.validation.geometry.geometry_validation import (
    GeometryValidationError,
    GeometryValidator,
)
from ast_engine.tests.unit.validation.validation_cases import frame, geometry_policy, rule

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "check,width,triggered",
    [
        ("min_area", 99, True),
        ("min_area", 100, False),
        ("min_area", 101, False),
        ("max_area", 99, False),
        ("max_area", 100, False),
        ("max_area", 101, True),
    ],
)
def test_area_threshold_is_in_hectares_and_equality_is_allowed(check, width, triggered):
    validator = GeometryValidator(
        geometry_policy(
            rule(
                check,
                rule_id="parcel_limit",
                threshold_ha=0.1,
                severity="warning",
                tags=[" Review ", "review"],
                message="{subject_id}: {actual:.3f} / {limit:.3f} ha",
            )
        )
    )
    findings = validator.validate(gdf=frame(box(0, 0, width, 10)), subject_ids=("piece-A",))
    assert isinstance(findings, tuple)
    if not triggered:
        assert findings == ()
        return
    (finding,) = findings
    assert (finding.code, finding.rule_id) == ("PARCEL_LIMIT", check.upper())
    assert (finding.category, finding.severity, finding.scope, finding.subject_id) == (
        "geometry",
        "warning",
        "part",
        "piece-A",
    )
    assert finding.message == f"piece-A: {width / 1000:.3f} / 0.100 ha"
    assert finding.tags == ("review",)
    assert not finding.is_blocking


def test_footprint_area_uses_union_and_footprint_id():
    rows = frame(box(0, 0, 10, 10), box(5, 0, 15, 10))  # sum .020 ha, union .015 ha
    config = geometry_policy(
        rule("max_area", rule_id="part_cap", threshold_ha=0.009),
        rule(
            "max_area",
            rule_id="foot_cap",
            scope="footprint",
            threshold_ha=0.014,
            message="{subject_id}: {actual:.3f} ha",
        ),
        rule("max_area", rule_id="looser_cap", scope="footprint", threshold_ha=0.016),
    )
    found = GeometryValidator(config).validate(
        gdf=rows, subject_ids=("left", "right"), footprint_id="P"
    )
    assert [(f.code, f.subject_id) for f in found] == [
        ("PART_CAP", "left"),
        ("PART_CAP", "right"),
        ("FOOT_CAP", "P"),
    ]
    assert found[-1].scope == "footprint" and found[-1].message == "P: 0.015 ha"


@pytest.mark.parametrize("limit,triggered", [(9, True), (10, False)])
def test_vertex_limit_counts_holes_and_closing_coordinates(limit, triggered):
    geom = Polygon(box(0, 0, 10, 10).exterior.coords, [box(2, 2, 4, 4).exterior.coords])
    validator = GeometryValidator(geometry_policy(rule("max_vertices", threshold=limit)))
    found = validator.validate(gdf=frame(geom), subject_ids=("ring",))
    if triggered:
        (finding,) = found
        assert finding.subject_id == "ring" and "10 vertices" in finding.message
    else:
        assert found == ()


@pytest.mark.parametrize(
    "count,expected",
    [
        (50, []),
        (51, [("PART_COUNT_WARNING", "warning")]),
        (500, [("PART_COUNT_WARNING", "warning")]),
        (501, [("PART_COUNT_WARNING", "warning"), ("PART_COUNT_LIMIT", "error")]),
    ],
)
def test_all_parts_reports_once_per_triggered_rule_without_requiring_part_ids(count, expected):
    policy = geometry_policy(
        rule(
            "max_part_count",
            rule_id="part_count_warning",
            scope="all_parts",
            severity="warning",
            threshold=50,
        ),
        rule("max_part_count", rule_id="part_count_limit", scope="all_parts", threshold=500),
    )
    rows = frame(*(box(2 * i, 0, 2 * i + 1, 1) for i in range(count)))
    found = GeometryValidator(policy).validate(gdf=rows, footprint_id="whole")
    assert [(f.code, f.severity) for f in found] == expected
    assert all(
        (f.scope, f.subject_id, f.rule_id) == ("all_parts", "whole", "MAX_PART_COUNT")
        and f"contains {count} parts" in f.message
        for f in found
    )


@pytest.mark.parametrize(
    "ids,reason",
    [
        (None, "require subject_ids"),
        ((), "one unique"),
        (("a", "b"), "one unique"),
        ((" ",), "one unique"),
    ],
)
def test_part_rules_require_one_nonblank_id_per_row(ids, reason):
    validator = GeometryValidator(geometry_policy(rule(threshold_ha=0.1)))
    with pytest.raises(GeometryValidationError, match=reason):
        validator.validate(gdf=frame(box(0, 0, 10, 10)), subject_ids=ids)


@pytest.mark.parametrize(
    "input_frame,cause",
    [
        (frame(box(0, 0, 1, 1), crs="EPSG:4326"), DataCRSError),
        (frame(Polygon([(0, 0), (1, 1), (0, 1), (1, 0), (0, 0)])), SpatialGeometryError),
        (frame(), SpatialDataError),
    ],
    ids=["geographic-crs", "self-intersection", "zero-rows"],
)
def test_frame_failures_become_geometry_execution_errors(input_frame, cause):
    # A footprint-only rule avoids hiding an input failure behind a bad subject_ids tuple.
    validator = GeometryValidator(geometry_policy(rule(scope="footprint", threshold_ha=0.1)))
    with pytest.raises(GeometryValidationError) as error:
        validator.validate(gdf=input_frame)
    assert isinstance(error.value.__cause__, cause)


@pytest.mark.parametrize(
    "message", ["", "{unknown}", "{actual.real}", "{actual:{limit}}", "{actual:.1000000000f}", "{"]
)
def test_bad_message_template_is_rejected_before_execution(message):
    with pytest.raises(ValidationError, match="Invalid message template|cannot be blank"):
        geometry_policy(rule(threshold_ha=0.1, message=message))


def test_footprint_vertices_are_measured_on_the_union():
    # Adjacent boxes each have five coordinates; their union has seven, not ten.
    val = GeometryValidator(
        geometry_policy(
            rule("max_vertices", rule_id="lower", scope="footprint", threshold=6),
            rule("max_vertices", rule_id="equal", scope="footprint", threshold=7),
        )
    )
    (finding,) = val.validate(gdf=frame(box(0, 0, 10, 10), box(10, 0, 20, 10)), footprint_id="P")
    assert (finding.code, finding.subject_id) == ("LOWER", "P")
    assert "7 vertices" in finding.message


@pytest.mark.parametrize(
    "bad_rule",
    [
        rule(threshold_ha=-1),
        rule(threshold_ha=float("nan")),
        rule(scope="all_parts", threshold_ha=1),
        rule("max_part_count", scope="part", threshold=5),
        rule("max_part_count", scope="all_parts", threshold=True),
        rule("max_vertices", threshold=2),
    ],
)
def test_geometry_rule_rejects_bad_threshold_or_incompatible_scope(bad_rule):
    with pytest.raises(ValidationError):
        geometry_policy(bad_rule)
