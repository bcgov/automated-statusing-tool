from string import Formatter
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..schema import Tags, ValidationProfile, ValidationScope, ValidationSeverity


class GeometryRuleBase(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    id: str = Field(min_length=1)
    scope: ValidationScope
    severity: ValidationSeverity
    run_in: tuple[ValidationProfile, ...] = (
        ValidationProfile.SUBMISSION, 
        ValidationProfile.RUNTIME
    )
    message: str | None = None
    tags: Tags = ()

    @field_validator("run_in")
    @classmethod
    def validate_profiles(cls, values):
        if not values or len(set(values)) != len(values):
            raise ValueError("run_in must contain unique, nonempty profile names.")
        return values

    @model_validator(mode="after")
    def validate_template(self):
        if self.message is None:
            return self
        if not self.message:
            raise ValueError("A supplied message cannot be blank.")
        values = {"subject_id": "part-1", "scope": self.scope, "actual": 1, "limit": 2}
        try:
            for _, name, spec, conversion in Formatter().parse(self.message):
                spec = spec or ""
                if name is not None and name not in values:
                    raise ValueError(f"Unsupported message placeholder: {name!r}.")
                if "{" in spec or "}" in spec or len(spec) > 20:
                    raise ValueError(
                        "Nested or excessive format specifications are unsupported."
                    )
                # Keep numeric field widths/precisions bounded before test-formatting.
                import re

                if any(int(n) > 1000 for n in re.findall(r"\d+", spec)):
                    raise ValueError(
                        "Message format widths/precisions must be at most 1000."
                    )
            if getattr(self, "check", None) in {"min_area", "max_area"}:
                values.update(actual=1.5, limit=2.5)
            self.message.format(**values)
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError(
                f"Invalid message template for rule {self.id!r}: {exc}"
            ) from exc
        return self


class AreaRule(GeometryRuleBase):
    check: Literal["min_area", "max_area"]
    scope: Literal[
        ValidationScope.PART,
        ValidationScope.FOOTPRINT,
    ]
    threshold_ha: float = Field(
        ge=0,
        strict=True,
        allow_inf_nan=False,
    )


class MaxVerticesRule(GeometryRuleBase):
    check: Literal["max_vertices"]
    scope: Literal[
        ValidationScope.PART,
        ValidationScope.FOOTPRINT,
    ]
    threshold: int = Field(ge=3, strict=True)


class MaxPartCountRule(GeometryRuleBase):
    check: Literal["max_part_count"]
    scope: Literal[ValidationScope.ALL_PARTS]
    threshold: int = Field(ge=1, strict=True)


GeometryRule = Annotated[
    AreaRule | MaxVerticesRule | MaxPartCountRule,
    Field(discriminator="check")
]


class GeometryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    rules: tuple[GeometryRule, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_rule_ids(self):
        ids = [rule.id for rule in self.rules]
        if len(ids) != len(set(ids)):
            raise ValueError("Geometry rule IDs must be unique.")
        return self
