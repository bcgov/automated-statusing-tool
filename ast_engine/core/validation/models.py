"""One policy type, instantiated separately for AOI and results validation."""

from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
    computed_field,
)

from ast_engine.core.validation.schema import (
    NonEmptyString,
    ValidationCategory,
    ValidationProfile,
    ValidationScope,
    ValidationSeverity,
    Tags,
)
from .geometry.models import GeometryConfig
from .spatial.models import SpatialLayerReferenceConfig

class ValidationConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    profile: ValidationProfile = ValidationProfile.RUNTIME
    spatial: tuple[SpatialLayerReferenceConfig, ...] | None = Field(
        default=None, min_length=1
    )
    geometry: GeometryConfig | None = None

    @field_validator("schema_version", mode="before")
    @classmethod
    def require_integer_version(cls, value: object) -> int:
        if type(value) is not int:
            raise ValueError("schema_version must be an integer.")
        return value

    @model_validator(mode="after")
    def unique_names(self):
        names = [layer.name for layer in self.spatial or ()]
        if len(names) != len(set(names)):
            raise ValueError("Validation layer names must be unique.")
        return self


class ValidationIssue(BaseModel):
    """One validation finding, classified by severity, category, scope, and tags."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        str_strip_whitespace=True,
    )

    severity: ValidationSeverity
    code: NonEmptyString
    message: NonEmptyString
    layer_name: NonEmptyString | None = None
    subject_id: NonEmptyString
    category: ValidationCategory
    scope: ValidationScope
    rule_id: NonEmptyString
    tags: Tags = ()

    @field_validator("severity", "category", "scope", mode="before")
    @classmethod
    def normalize_enum_text(cls, value: object) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                "Must be a nonblank string or string enum member."
            )
        return value.strip().lower()

    @field_validator("code", mode="after")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.upper()

    @computed_field
    @property
    def is_blocking(self) -> bool:
        return self.severity == ValidationSeverity.ERROR
