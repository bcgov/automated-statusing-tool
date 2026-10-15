from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from pyproj import CRS

from ast_engine.core.aoi.exceptions import AOIRequestError
from ast_engine.core.aoi.models import AOIRequest
from ast_engine.tests.helpers.aoi_requests import make_aoi_request


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


# ============================================================
# Valid construction and defaults
# ============================================================

def test_request_uses_expected_defaults():
    """Test that the AOIRequest factory produces an object with the expected default values."""

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
    """Test that the AOIRequest exposes properties for the resolved CRS and EPSG code."""

    request = make_aoi_request()

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
    """Test that the AOIRequest accepts supported dissolve modes and fields."""

    request = make_aoi_request(
        dissolve_mode=dissolve_mode,
        dissolve_fields=dissolve_fields,
    )

    assert request.dissolve_mode == dissolve_mode
    assert request.dissolve_fields == dissolve_fields


@pytest.mark.parametrize("allow_overlaps", [True, False])

def test_request_accepts_boolean_overlap_policy(
    allow_overlaps,
):
    """Test that the AOIRequest accepts a boolean value for the allow_overlaps parameter."""

    request = make_aoi_request(
        allow_overlaps=allow_overlaps,
    )

    assert request.allow_overlaps is allow_overlaps


# ============================================================
# Value normalization
# ============================================================

def test_request_normalizes_identifier_and_name():
    request = make_aoi_request(
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
    """Test that the AOIRequest normalizes the dissolve_mode to lowercase and strips whitespace."""

    dissolve_fields = (
        ("REGION",)
        if expected == "by_fields"
        else ()
    )

    request = make_aoi_request(
        dissolve_mode=input_mode,
        dissolve_fields=dissolve_fields,
    )

    assert request.dissolve_mode == expected


def test_request_normalizes_dissolve_fields_to_tuple():
    """Test that the AOIRequest normalizes the dissolve_fields to a tuple of stripped strings."""

    request = make_aoi_request(
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
    """Test that the AOIRequest removes blank dissolve_fields for non-field policies like "full_union" and "preserve_features"."""

    request = make_aoi_request(
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
    """Test that the AOIRequest rejects non-string types for the aoi_id and name fields."""

    with pytest.raises(
        AOIRequestError,
        match=message,
    ):
        make_aoi_request(**{field_name: value})


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
    """Test that the AOIRequest rejects blank strings for the aoi_id and name fields."""

    with pytest.raises(
        AOIRequestError,
        match=message,
    ):
        make_aoi_request(**{field_name: value})


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
    """Test that the AOIRequest rejects unsupported dissolve_mode values."""

    with pytest.raises(
        AOIRequestError,
        match="Unsupported AOIRequest.dissolve_mode",
    ):
        make_aoi_request(
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
    """Test that the AOIRequest rejects non-string types for the dissolve_mode field."""

    with pytest.raises(
        AOIRequestError,
        match="dissolve_mode must be a string",
    ):
        make_aoi_request(
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
    """Test that the AOIRequest rejects empty dissolve_fields when dissolve_mode is 'by_fields'."""
    with pytest.raises(
        AOIRequestError,
        match="dissolve_fields must be provided",
    ):
        make_aoi_request(
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
    """Test that the AOIRequest rejects dissolve_fields for non-field policies."""

    with pytest.raises(
        AOIRequestError,
        match="should only be provided",
    ):
        make_aoi_request(
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
    """Test that the AOIRequest rejects non-sequence types for the dissolve_fields parameter."""

    with pytest.raises(
        AOIRequestError,
        match="must be a sequence of strings",
    ):
        make_aoi_request(
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
    """Test that the AOIRequest rejects non-string values in the dissolve_fields sequence."""
    
    with pytest.raises(
        AOIRequestError,
        match="must contain only strings",
    ):
        make_aoi_request(
            dissolve_mode="by_fields",
            dissolve_fields=dissolve_fields,
        )


# ============================================================
# CRS validation
# ============================================================

def test_request_accepts_alternative_metric_projected_crs():
    """Test that the AOIRequest accepts a valid alternative metric projected CRS."""

    request = make_aoi_request(
        target_crs="EPSG:26910",
    )

    assert request.is_projected is True
    assert request.target_epsg == 26910


def test_request_rejects_invalid_crs():
    """Test that the AOIRequest rejects an invalid CRS string."""

    with pytest.raises(
        AOIRequestError,
        match="Invalid AOIRequest.target_crs",
    ) as exc_info:
        make_aoi_request(
            target_crs="not-a-real-crs",
        )

    assert exc_info.value.__cause__ is not None


def test_request_rejects_geographic_crs():
    with pytest.raises(
        AOIRequestError,
        match="target_crs must be projected",
    ):
        """Test that the AOIRequest rejects a geographic (unprojected) CRS."""

        make_aoi_request(
            target_crs="EPSG:4326",
        )


def test_request_rejects_non_string_crs():
    with pytest.raises(
        AOIRequestError,
        match="target_crs must be a string",
    ):
        """Test that the AOIRequest rejects a non-string target_crs value."""

        make_aoi_request(
            target_crs=3005,
        )


def test_request_rejects_non_metric_projected_crs():
    """Test that the AOIRequest rejects a projected CRS that does not use metres as its unit.
       EPSG:2263 is projected but uses US survey feet.
    """

    with pytest.raises(
        AOIRequestError,
        match="must use metres",
    ):
        make_aoi_request(
            target_crs="EPSG:2263",
        )


def test_custom_metric_crs_may_have_no_epsg_code():
    """Test that the AOIRequest accepts a custom metric projected CRS that has no EPSG code."""

    request = make_aoi_request(
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
        make_aoi_request(
            allow_overlaps=allow_overlaps,
        )


# ============================================================
# Immutability
# ============================================================

def test_request_is_immutable():
    """Test that the AOIRequest is immutable and cannot be modified after creation."""

    request = make_aoi_request()

    with pytest.raises(FrozenInstanceError):
        request.name = "Changed name"


def test_normalized_dissolve_fields_are_immutable():
    """Test that the normalized dissolve_fields tuple is immutable and cannot be modified after creation."""

    request = make_aoi_request(
        dissolve_mode="by_fields",
        dissolve_fields=["REGION"],
    )

    assert request.dissolve_fields == ("REGION",)

    with pytest.raises(TypeError):
        request.dissolve_fields[0] = "OTHER"