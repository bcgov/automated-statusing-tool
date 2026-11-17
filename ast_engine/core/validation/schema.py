from collections.abc import Mapping
from enum import StrEnum
from typing import Annotated
from pydantic import (
    AfterValidator,
    Field,
    StrictInt,
    StrictStr,
    BeforeValidator,
    StringConstraints,
    ValidatorFunctionWrapHandler,
    WrapValidator,
)


class ValidationSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class ValidationCategory(StrEnum):
    GEOMETRY = "geometry"
    SPATIAL = "spatial"


class ValidationScope(StrEnum):
    PART = "part"
    FOOTPRINT = "footprint"
    FEATURE = "feature"
    ALL_PARTS = "all_parts"


class ValidationProfile(StrEnum):
    SUBMISSION = "submission"
    RUNTIME = "runtime"


def _distinct_profiles(values: tuple[ValidationProfile, ...]) -> tuple[ValidationProfile, ...]:
    if len(values) != len(set(values)):
        raise ValueError("run_in must contain unique profile names.")
    return values


ReferenceUnitId = StrictStr | StrictInt

NonEmptyString = Annotated[str, Field(strict=True, min_length=1)]

RunIn = Annotated[
    tuple[ValidationProfile, ...], Field(min_length=1), AfterValidator(_distinct_profiles)
]

DEFAULT_RUN_IN = (ValidationProfile.SUBMISSION, ValidationProfile.RUNTIME)


######### TAGS #########

def _coerce_tag(value: object) -> object:
    # Convert integer labels, but do not convert True/False.
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)

    return value


Tag = Annotated[
    str,
    StringConstraints(
        strict=True,
        strip_whitespace=True,
        to_lower=True,
        min_length=1,
    ),
    BeforeValidator(
        _coerce_tag,
        json_schema_input_type=str | int,
    ),
]


def _normalize_tags(
    value: object,
    handler: ValidatorFunctionWrapHandler,
) -> tuple[str, ...]:
    unordered = isinstance(value, (set, frozenset))

    if isinstance(value, Mapping):
        raise ValueError(
            "Tags cannot be a mapping; pass its keys or values explicitly."
        )

    if isinstance(value, (str, int)) and not isinstance(value, bool):
        # A string becomes one tag, not a tuple of individual characters.
        value = (value,)

    elif not isinstance(value, (list, tuple, set, frozenset)):
        raise ValueError(
            "Tags must be a string, integer, list, tuple, or set."
        )

    # Run Pydantic's validation and normalization for every Tag.
    normalized = handler(tuple(value))

    # Remove duplicates after trimming, lowercasing, and integer conversion.
    unique = tuple(dict.fromkeys(normalized))

    return tuple(sorted(unique)) if unordered else unique


Tags = Annotated[
    tuple[Tag, ...],
    WrapValidator(
        _normalize_tags,
        json_schema_input_type=str | int | list[str | int],
    ),
]