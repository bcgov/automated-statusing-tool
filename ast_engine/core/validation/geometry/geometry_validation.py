"""Geometry policy checks on supplied frames; no AOI, settings or data access."""

import geopandas as gpd
import logging
from shapely import get_num_coordinates

from ast_engine.core.exceptions import SpatialDataError, DataCRSError, SpatialGeometryError
from ast_engine.utils.spatial_checks import check_polygon_frame

from ..models import ValidationIssue
from ..schema import (
    ValidationCategory,
    ValidationProfile,
    ValidationScope,
)
from ..common import check_subject_ids
from .models import GeometryConfig


logger = logging.getLogger(__name__)

DEFAULT_MESSAGES = {
    "min_area": "{scope} {subject_id}: area {actual:.3f} ha is below {limit:.3f} ha.",
    "max_area": "{scope} {subject_id}: area {actual:.3f} ha exceeds {limit:.3f} ha.",
    "max_vertices": "{scope} {subject_id}: {actual} vertices exceeds {limit}.",
    "max_part_count": "AOI {subject_id} contains {actual} parts; the maximum is {limit}.",
}


class GeometryValidationError(ValueError):
    """A geometry check could not execute; a geometric rule failure is a finding."""


class GeometryValidator:
    def __init__(
            self,
            config: GeometryConfig,
            *,
            profile: ValidationProfile = ValidationProfile.RUNTIME,
    ) -> None:
        try:
            self.profile = ValidationProfile(profile)
        except ValueError as exc:
            raise GeometryValidationError(f"Unknown vlaidation profile: {profile!r}.") from exc
        self.config = config
        self.active_rules = tuple(
            rule for rule in config.rules if self.profile in rule.run_in
        )

    def validate(
        self,
        *,
        gdf: gpd.GeoDataFrame,
        subject_ids: tuple[str, ...] | None = None,
        footprint_id: str = "footprint",
    ) -> tuple[ValidationIssue, ...]:
        if not self.active_rules:
            logger.debug("Geometry Validation contains no active rules")
            return ()
        
        logger.debug(
            "Validating Geometry for %s containing %s features.", 
            footprint_id, len(gdf)
        )
                    
        try:
            check_polygon_frame(
                gdf, label="Geometry validation subject", require_metric=True
            )
        except (SpatialDataError, DataCRSError, SpatialGeometryError) as exc:
            raise GeometryValidationError(str(exc)) from exc

        try:
            check_subject_ids(gdf, subject_ids)

            logger.debug("GDF frame and ID's pre-check complete.")

            scopes = {rule.scope for rule in self.active_rules}
            subjects = {}
            if ValidationScope.PART in scopes:
                if subject_ids is None:
                    raise GeometryValidationError("Part-scoped geometry rules require subject_ids.")
                subjects[ValidationScope.PART] = tuple(zip(subject_ids, gdf.geometry, strict=True))
            if ValidationScope.FOOTPRINT in scopes:
                subjects[ValidationScope.FOOTPRINT] = ((footprint_id, gdf.geometry.union_all()),)
            # Matches AOIPart's existing convention: exterior + holes, closing coordinates included.
            measures = {
                scope: tuple(
                    (name, float(geom.area / 10000), int(get_num_coordinates(geom)))
                    for name, geom in entries
                )
                for scope, entries in subjects.items()
            }
            issues = []
            part_count = len(gdf)
            for rule in self.active_rules:
                if rule.check == "max_part_count":
                    actual, limit = part_count, rule.threshold
                    triggered = actual > limit

                    if triggered:
                        template = rule.message or DEFAULT_MESSAGES[rule.check]

                        issues.append(
                            ValidationIssue(
                                severity=rule.severity,
                                code=rule.id,
                                rule_id=rule.check.upper(),
                                category=ValidationCategory.GEOMETRY,
                                scope=rule.scope,
                                subject_id=footprint_id,
                                tags=rule.tags,
                                message=template.format(
                                    subject_id=footprint_id,
                                    scope=rule.scope,
                                    actual=actual,
                                    limit=limit,
                                ),
                            )
                        )

                    continue
                for name, area, vertices in measures[rule.scope]:
                    if rule.check == "min_area":
                        actual, limit = area, rule.threshold_ha
                        triggered = actual < limit
                    elif rule.check == "max_area":
                        actual, limit = area, rule.threshold_ha
                        triggered = actual > limit
                    elif rule.check == "max_vertices":
                        actual, limit = vertices, rule.threshold
                        triggered = actual > limit
                    else:
                        raise GeometryValidationError(f"Unsupported geometry check: {rule.check!r}.")
                    if triggered:
                        template = rule.message or DEFAULT_MESSAGES[rule.check]
                        issues.append(
                            ValidationIssue(
                                severity=rule.severity,
                                code=rule.id,
                                rule_id=rule.check.upper(),
                                category="geometry",
                                scope=rule.scope,
                                subject_id=name,
                                tags=rule.tags,
                                message=template.format(
                                    subject_id=name,
                                    scope=rule.scope,
                                    actual=actual,
                                    limit=limit,
                                ),
                            )
                        )
            return tuple(issues)
        except (ValueError, TypeError) as exc:
            raise GeometryValidationError(
                f"Geometry validation could not execute: {exc}"
            ) from exc
