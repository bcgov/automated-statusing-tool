from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Any

import pytest
from pyproj import CRS

from ast_engine.core.aoi.exceptions import AOIRequestError
from ast_engine.core.aoi.models import AOIRequest


pytestmark = pytest.mark.unit


CUSTOM_METRIC_CRS = (
    "+proj=tmerc "
    "+lat_0=0 "
    "+lon_0=-123.4567 "
    "+k=0.9999 "
    "+x_0=12345 "
    "+y_0=67890 "
    "+datum=WGS84 "
    "+units=m "
    "+no_defs "
    "+type=crs"
)


def make_request(**overrides: Any) -> AOIRequest:
    """
    Build a valid request, replacing only the fields relevant to a test.
    """
    values: dict[str, Any] = {
        "aoi_id": "test_aoi",
        "name": "Test AOI",
        "target_crs": "EPSG:3005",
        "dissolve_mode": "full_union",
        "dissolve_fields": (),
        "allow_overlaps": False,
    }

    values.update(overrides)

    return AOIRequest(**values)


# ============================================================
# Valid construction and defaults
# ============================================================

def test_request_uses_expected_defaults():
    request = AOIRequest(
        aoi_id="test_aoi",
        name="Test AOI",
    )

    assert request.aoi_id == "test_aoi"
    assert request.name == "Test AOI"
    assert request.target_crs == "EPSG:3005"
    assert request.dissolve_mode == "full_union"
    assert request.dissolve_fields == ()
    assert request.allow_overlaps is False


def test_request_exposes_resolved_crs_properties():
    request = make_request()

    assert isinstance(request.target_crs_obj, CRS)
    assert request.target_crs_obj.equals(CRS.from_epsg(3005))
    assert request.target_epsg == 3005
    assert request.is_projected is True


@pytest.mark.parametrize(
    ("dissolve_mode", "dissolve_fields"),
    [
        ("full_union", ()),
        ("by_fields", ("REGION",)),
        ("preserve_features", ()),
    ],
)
def test_request_accepts_supported_dissolve_modes(
    dissolve_mode,
    dissolve_fields,
):
    request = make_request(
        dissolve_mode=dissolve_mode,
        dissolve_fields=dissolve_fields,
    )

    assert request.dissolve_mode == dissolve_mode
    assert request.dissolve_fields == dissolve_fields


@pytest.mark.parametrize("allow_overlaps", [True, False])
def test_request_accepts_boolean_overlap_policy(
    allow_overlaps,
):
    request = make_request(
        allow_overlaps=allow_overlaps,
    )

    assert request.allow_overlaps is allow_overlaps


# ============================================================
# Value normalization
# ============================================================

def test_request_normalizes_identifier_and_name():
    request = make_request(
        aoi_id="  test123  ",
        name="  Test AOI Name  ",
    )

    assert request.aoi_id == "test123"
    assert request.name == "Test AOI Name"


@pytest.mark.parametrize(
    ("input_mode", "expected"),
    [
        ("FULL_UNION", "full_union"),
        (" full_union ", "full_union"),
        ("BY_FIELDS", "by_fields"),
        (" preserve_features ", "preserve_features"),
    ],
)
def test_request_normalizes_dissolve_mode(
    input_mode,
    expected,
):
    dissolve_fields = (
        ("REGION",)
        if expected == "by_fields"
        else ()
    )

    request = make_request(
        dissolve_mode=input_mode,
        dissolve_fields=dissolve_fields,
    )

    assert request.dissolve_mode == expected


def test_request_normalizes_dissolve_fields_to_tuple():
    request = make_request(
        dissolve_mode="by_fields",
        dissolve_fields=[
            " REGION ",
            "",
            "  ",
            "UNIT_NAME ",
        ],
    )

    assert request.dissolve_fields == (
        "REGION",
        "UNIT_NAME",
    )
    assert isinstance(request.dissolve_fields, tuple)


def test_request_removes_blank_fields_for_non_field_policy():
    request = make_request(
        dissolve_mode="full_union",
        dissolve_fields=(" ", ""),
    )

    assert request.dissolve_fields == ()


# ============================================================
# Identifier and name validation
# ============================================================

@pytest.mark.parametrize(
    ("field_name", "value", "message"),
    [
        (
            "aoi_id",
            None,
            "AOIRequest.aoi_id must be a string",
        ),
        (
            "aoi_id",
            123,
            "AOIRequest.aoi_id must be a string",
        ),
        (
            "name",
            None,
            "AOIRequest.name must be a string",
        ),
        (
            "name",
            123,
            "AOIRequest.name must be a string",
        ),
    ],
)
def test_request_rejects_invalid_text_types(
    field_name,
    value,
    message,
):
    with pytest.raises(
        AOIRequestError,
        match=message,
    ):
        make_request(**{field_name: value})


@pytest.mark.parametrize(
    ("field_name", "value", "message"),
    [
        (
            "aoi_id",
            "",
            "AOIRequest.aoi_id cannot be empty",
        ),
        (
            "aoi_id",
            "   ",
            "AOIRequest.aoi_id cannot be empty",
        ),
        (
            "name",
            "",
            "AOIRequest.name cannot be empty",
        ),
        (
            "name",
            "   ",
            "AOIRequest.name cannot be empty",
        ),
    ],
)
def test_request_rejects_blank_required_text(
    field_name,
    value,
    message,
):
    with pytest.raises(
        AOIRequestError,
        match=message,
    ):
        make_request(**{field_name: value})


# ============================================================
# Dissolve-mode validation
# ============================================================

@pytest.mark.parametrize(
    "dissolve_mode",
    [
        "merge",
        "union",
        "preserve",
        "",
        "   ",
    ],
)
def test_request_rejects_unsupported_dissolve_mode(
    dissolve_mode,
):
    with pytest.raises(
        AOIRequestError,
        match="Unsupported AOIRequest.dissolve_mode",
    ):
        make_request(
            dissolve_mode=dissolve_mode,
        )


@pytest.mark.parametrize(
    "dissolve_mode",
    [
        None,
        1,
        True,
        object(),
    ],
)
def test_request_rejects_non_string_dissolve_mode(
    dissolve_mode,
):
    with pytest.raises(
        AOIRequestError,
        match="dissolve_mode must be a string",
    ):
        make_request(
            dissolve_mode=dissolve_mode,
        )


@pytest.mark.parametrize(
    "dissolve_fields",
    [
        (),
        [],
        ("",),
        (" ",),
    ],
)
def test_by_fields_requires_nonempty_dissolve_fields(
    dissolve_fields,
):
    with pytest.raises(
        AOIRequestError,
        match="dissolve_fields must be provided",
    ):
        make_request(
            dissolve_mode="by_fields",
            dissolve_fields=dissolve_fields,
        )


@pytest.mark.parametrize(
    "dissolve_mode",
    [
        "full_union",
        "preserve_features",
    ],
)
def test_non_field_modes_reject_dissolve_fields(
    dissolve_mode,
):
    with pytest.raises(
        AOIRequestError,
        match="should only be provided",
    ):
        make_request(
            dissolve_mode=dissolve_mode,
            dissolve_fields=("REGION",),
        )


@pytest.mark.parametrize(
    "dissolve_fields",
    [
        None,
        "REGION",
        {"REGION"},
        123,
    ],
)
def test_request_rejects_invalid_dissolve_fields_container(
    dissolve_fields,
):
    with pytest.raises(
        AOIRequestError,
        match="must be a sequence of strings",
    ):
        make_request(
            dissolve_mode="by_fields",
            dissolve_fields=dissolve_fields,
        )


@pytest.mark.parametrize(
    "dissolve_fields",
    [
        ("REGION", 123),
        ("REGION", None),
        (True,),
    ],
)
def test_request_rejects_non_string_dissolve_fields(
    dissolve_fields,
):
    with pytest.raises(
        AOIRequestError,
        match="must contain only strings",
    ):
        make_request(
            dissolve_mode="by_fields",
            dissolve_fields=dissolve_fields,
        )


# ============================================================
# CRS validation
# ============================================================

# def test_request_accepts_alternative_metric_projected_crs():
#     request = make_request(
#         target_crs="EPSG:26910",
#     )

#     assert request.is_projected is True
#     assert request.target_epsg == 26910


def test_request_rejects_invalid_crs():
    with pytest.raises(
        AOIRequestError,
        match="Invalid AOIRequest.target_crs",
    ) as exc_info:
        make_request(
            target_crs="not-a-real-crs",
        )

    # Confirm the underlying pyproj failure is preserved.
    assert exc_info.value.__cause__ is not None


def test_request_rejects_geographic_crs():
    with pytest.raises(
        AOIRequestError,
        match="target_crs must be projected",
    ):
        make_request(
            target_crs="EPSG:4326",
        )


def test_request_rejects_non_string_crs():
    with pytest.raises(
        AOIRequestError,
        match="target_crs must be a string",
    ):
        make_request(
            target_crs=3005,
        )


# def test_request_rejects_non_metric_projected_crs():
#     # EPSG:2263 is projected but uses US survey feet.
#     with pytest.raises(
#         AOIRequestError,
#         match="must use metres",
#     ):
#         make_request(
#             target_crs="EPSG:2263",
#         )


def test_custom_metric_crs_may_have_no_epsg_code():
    request = make_request(
        target_crs=CUSTOM_METRIC_CRS,
    )

    assert request.is_projected is True
    assert request.target_epsg is None
    assert request.target_crs_obj.axis_info[0].unit_name in {
        "metre",
        "meter",
    }


# ============================================================
# Overlap policy validation
# ============================================================

@pytest.mark.parametrize(
    "allow_overlaps",
    [
        None,
        0,
        1,
        "true",
        "false",
    ],
)
def test_request_rejects_non_boolean_overlap_policy(
    allow_overlaps,
):
    with pytest.raises(
        AOIRequestError,
        match="allow_overlaps must be a boolean",
    ):
        make_request(
            allow_overlaps=allow_overlaps,
        )


# ============================================================
# Immutability
# ============================================================

def test_request_is_immutable():
    request = make_request()

    with pytest.raises(FrozenInstanceError):
        request.name = "Changed name"  # type: ignore[misc]


def test_normalized_dissolve_fields_are_immutable():
    request = make_request(
        dissolve_mode="by_fields",
        dissolve_fields=["REGION"],
    )

    assert request.dissolve_fields == ("REGION",)

    with pytest.raises(TypeError):
        request.dissolve_fields[0] = "OTHER"  # type: ignore[index]