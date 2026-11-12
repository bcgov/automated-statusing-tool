"""Spatial rule configuration; imports shared contracts, not the parent model."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..common import (
    checked_unit_ids,
)
from ..schema import (
    NonEmptyString,
    ReferenceUnitId,
    Tags,
    ValidationProfile,
    ValidationSeverity,
    ValidationScope,
)

class SpatialRuleConfig(BaseModel):
    """A severity enables a check; omitted/null checks are disabled."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    overlap: ValidationSeverity | None = None
    no_overlap: ValidationSeverity | None = None
    partial_outside: ValidationSeverity | None = None
    multiple_units: ValidationSeverity | None = None
    outside_expected: ValidationSeverity | None = None

    @model_validator(mode="after")
    def require_enabled_rule(self):
        if all(value is None for value in self.model_dump().values()):
            raise ValueError("A reference layer must enable at least one spatial rule.")
        return self


class SpatialLayerReferenceConfig(BaseModel):
    """One polygon reference source. File paths are resolved by the loader."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    name: NonEmptyString
    data_adapter: Literal["oracle", "file"]
    datasource: NonEmptyString
    run_in: tuple[ValidationProfile, ...] = (
        ValidationProfile.SUBMISSION, 
        ValidationProfile.RUNTIME
    )
    tags: Tags = ()
    scope: Literal[
        ValidationScope.PART,
        ValidationScope.FOOTPRINT,
    ]
    id_field: NonEmptyString | None = None
    expected_ids: tuple[ReferenceUnitId, ...] = ()
    expected_from: NonEmptyString | None = None
    area_tolerance_m2: float = Field(
        default=0.0, ge=0, allow_inf_nan=False, strict=True
    )
    rules: SpatialRuleConfig

    @field_validator("run_in")
    @classmethod
    def validate_profiles(cls, values):
        if not values or len(set(values)) != len(values):
            raise ValueError("run_in must contain unique, nonempty profile names.")
        return values

    @field_validator("expected_ids", mode="before")
    @classmethod
    def validate_ids(cls, values):
        return checked_unit_ids(values)

    @model_validator(mode="after")
    def validate_rule_inputs(self):
        if self.expected_ids and self.expected_from:
            raise ValueError("Use expected_ids or expected_from, not both.")
        needs_ids = (
            self.rules.multiple_units is not None
            or self.rules.outside_expected is not None
        )
        if needs_ids and self.id_field is None:
            raise ValueError("Reference unit checks require id_field.")
        has_expected = bool(self.expected_ids) or self.expected_from is not None
        if self.rules.outside_expected is not None and not has_expected:
            raise ValueError("outside_expected requires expected_ids or expected_from.")
        if has_expected and self.rules.outside_expected is None:
            raise ValueError("Expected IDs require outside_expected to be enabled.")
        return self