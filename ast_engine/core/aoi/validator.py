"""Coordinate AOI preconditions and independent geometry/spatial policies."""

from collections.abc import Mapping, Sequence

import geopandas as gpd
from ast_engine.core.validation.schema import(
    ValidationProfile,
)
from ast_engine.core.validation.spatial.spatial_validation import (
    SpatialValidationError,
)
from ast_engine.core.validation.geometry.geometry_validation import (
    GeometryValidationError,
)
from ast_engine.core.validation.geometry.geometry_validation import GeometryValidator
from ast_engine.core.validation.spatial.spatial_validation import SpatialValidator

from .exceptions import AOIValidationError
from .models import AOIPart, AOIValidationResult


class AOIValidator:
    def __init__(
        self,
        *,
        geometry_validator: GeometryValidator | None = None,
        spatial_validator: SpatialValidator | None = None,
        profile: ValidationProfile = ValidationProfile.RUNTIME,
    ) -> None:
        try:
            self.profile = ValidationProfile(profile)
        except ValueError as exc:
            raise AOIValidationError(f"Unknown validation profile: {profile!r}.") from exc
        for kind, child in (("geometry", geometry_validator), ("spatial", spatial_validator)):
            if child is not None and child.profile != self.profile:
                raise AOIValidationError(
                    f"AOI and {kind} validators must use the same profile "
                    f"(AOI={self.profile}, {kind}={child.profile})."
                )

        self.geometry_validator = geometry_validator
        self.spatial_validator = spatial_validator

    @property
    def required_spatial_parameters(self) -> frozenset[str]:
        if self.spatial_validator is None:
            return frozenset()

        return self.spatial_validator.required_parameters

    def validate(
        self,
        *,
        gdf: gpd.GeoDataFrame, # Normalized AOI geometry.
        parts: tuple[AOIPart, ...],
        aoi_id: str,
        parameters: Mapping[str, Sequence[str | int]] | None = None,
    ) -> AOIValidationResult:
        issues = []
        geometry_checks_run = False
        checked_layers = ()

        parts_gdf = gpd.GeoDataFrame(
            geometry=[part.geometry for part in parts], crs=gdf.crs
        )
        part_ids = tuple(part.part_id for part in parts)
        try:
            if self.spatial_validator is None and parameters:
                raise SpatialValidationError(
                    "Validation parameters were supplied while spatial validation is disabled."
                )
            if self.geometry_validator is not None and self.geometry_validator.active_rules:
                issues.extend(
                    self.geometry_validator.validate(
                        gdf=parts_gdf,
                        subject_ids=part_ids,
                        footprint_id=aoi_id,
                    )
                )
                geometry_checks_run = True
            # Policy errors (e.g. area too large) do not prevent collecting spatial findings.
            if self.spatial_validator is not None:
                issues.extend(
                    self.spatial_validator.validate(
                        gdf=parts_gdf,
                        subject_ids=part_ids,
                        footprint_id=aoi_id,
                        parameters=parameters,
                    )
                )
                checked_layers = tuple(
                    layer.name
                    for layer in self.spatial_validator.active_layers
                )
        except (GeometryValidationError, SpatialValidationError) as exc:
            # Execution failure is not a policy finding or a successful empty report.
            raise AOIValidationError(str(exc)) from exc

        return AOIValidationResult(
            issues=tuple(issues),
            geometry_checks_run=geometry_checks_run,
            spatial_checks_run=bool(checked_layers),
            checked_spatial_layers=checked_layers,
            profile=self.profile,
        )