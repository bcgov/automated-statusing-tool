"""Spatial policies evaluated against startup-cached polygon references."""

from collections.abc import Mapping, Sequence
from numbers import Integral

import geopandas as gpd
from pyproj import CRS
from pyproj.exceptions import ProjError
from shapely.errors import GEOSException

from ast_engine.core.exceptions import SpatialDataError, DataCRSError, SpatialGeometryError
from ast_engine.utils.spatial_checks import check_polygon_frame

from ..common import checked_unit_id
from ..models import  ValidationIssue
from ..schema import ValidationProfile
from ..common import check_subject_ids
from .models import SpatialLayerReferenceConfig
from .parameters import resolve_expected_ids


class SpatialValidationError(ValueError):
    """A spatial check could not execute; a geographic rule failure is a finding."""


class SpatialValidator:
    def __init__(
        self,
        config: tuple[SpatialLayerReferenceConfig, ...],
        *,
        reference_layers: Mapping[tuple[str, str], gpd.GeoDataFrame],
        target_crs: str = "EPSG:3005",
        profile: ValidationProfile = "runtime",
    ):
        if profile not in ValidationProfile:
            raise SpatialValidationError(f"Unknown validation profile: {profile!r}.")
        self.config = tuple(config)
        self.profile = profile
        self.target_crs = CRS.from_user_input(target_crs)
        self.active_layers = tuple(layer for layer in config if profile in layer.run_in)
        self._references = {}
        prepared = {}
        # Prepare ALL configured layers, including submission-only sources.
        for layer in self.config:
            source = (layer.data_adapter, layer.datasource)
            key = (*source, layer.id_field)
            if source not in reference_layers:
                raise SpatialValidationError(f"Reference {layer.name!r} is not cached.")
            try:
                if key not in prepared:
                    prepared[key] = self._prepare_reference(
                        reference_layers[source],
                        layer,
                        self.target_crs,
                    )
                    _ = prepared[
                        key
                    ].sindex  # Build before sharing across request threads.
                self._references[layer.name] = prepared[key]
                if layer.expected_ids:
                    self._check_expected_ids(layer, layer.expected_ids)
            except (ValueError, TypeError, GEOSException, ProjError, SpatialDataError) as exc:
                raise SpatialValidationError(
                    f"Could not prepare reference {layer.name!r}: {exc}"
                ) from exc

    @property
    def required_parameters(self) -> frozenset[str]:
        """Request parameters required by this profile's active rules."""
        return frozenset(
            layer.expected_from
            for layer in self.active_layers
            if layer.expected_from is not None
        )

    def _check_expected_ids(self, layer, values):
        if values and layer.id_field is not None:
            known = set(self._references[layer.name][layer.id_field].tolist())
            unknown = [value for value in values if value not in known]
            if unknown:
                raise SpatialValidationError(
                    f"Unknown expected IDs for {layer.name!r}: {unknown!r}."
                )

    def validate(
        self,
        *,
        gdf: gpd.GeoDataFrame,
        subject_ids: tuple[str, ...] | None = None,
        footprint_id: str = "footprint",
        parameters: Mapping[str, Sequence[str | int]] | None = None,
    ) -> tuple[ValidationIssue, ...]:
        try:
            self._check_frame(
                gdf, label="Spatial validation subject", require_metric=True
            )
            check_subject_ids(gdf, subject_ids)
            if gdf.crs != self.target_crs:
                raise SpatialDataError(
                    "Subject CRS differs from the prepared reference CRS."
                )
            expected = resolve_expected_ids(
                self.config, parameters, profile=self.profile
            )
            footprint = None
            issues = []
            for layer in self.active_layers:
                self._check_expected_ids(layer, expected[layer.name])
                if layer.scope == "part":
                    if subject_ids is None:
                        raise SpatialValidationError(
                            "Part-scoped spatial rules require subject_ids."
                        )
                    subjects = zip(subject_ids, gdf.geometry, strict=True)
                else:
                    if footprint is None:
                        footprint = gdf.geometry.union_all()
                    subjects = ((footprint_id, footprint),)
                for subject_id, geometry in subjects:
                    issues.extend(
                        self._evaluate(
                            geometry,
                            self._references[layer.name],
                            layer,
                            expected[layer.name],
                            f"{layer.scope} {subject_id}",
                            subject_id,
                        )
                    )
            return tuple(issues)
        except SpatialValidationError:
            raise
        except (ValueError, TypeError, GEOSException, ProjError, SpatialDataError) as exc:
            raise SpatialValidationError(
                f"Spatial validation could not execute: {exc}"
            ) from exc

    @classmethod
    def _prepare_reference(cls, gdf, layer, target_crs):
        label = f"Reference layer {layer.name!r}"
        cls._check_frame(gdf, label=label, allow_empty=True)
        geometry_name = gdf.geometry.name
        columns = [geometry_name]
        if layer.id_field is not None:
            if layer.id_field not in gdf.columns or layer.id_field == geometry_name:
                raise SpatialValidationError(
                    f"{label} has no ID field {layer.id_field!r}."
                )
            ids = gdf[layer.id_field]
            if ids.isna().any() or any(
                isinstance(value, bool)
                or not isinstance(value, (str, Integral))
                or (isinstance(value, str) and not value.strip())
                for value in ids
            ):
                raise SpatialValidationError(
                    f"{label} has null, blank, or non-integral IDs."
                )
            columns.append(layer.id_field)

        reference = gdf.loc[:, columns].copy(deep=True)
        if layer.id_field is not None:
            try:
                reference[layer.id_field] = reference[layer.id_field].map(
                    checked_unit_id
                )
            except ValueError as exc:
                raise SpatialValidationError(
                    f"{label}, field {layer.id_field!r}: {exc}"
                ) from exc
        if reference.crs != target_crs:
            reference = reference.to_crs(target_crs)
            cls._check_frame(reference, label=label, allow_empty=True)
        if layer.id_field is not None and not reference.empty:
            # Fragments with the same ID form one unit before applying tolerance.
            reference = reference.dissolve(
                by=layer.id_field, as_index=False, sort=False
            )
        return reference

    @staticmethod
    def _evaluate(footprint, reference, layer, expected_ids, subject, subject_id):
        positions = reference.sindex.query(footprint, predicate="intersects")
        candidates = reference.iloc[positions]
        coverage = candidates.geometry.union_all()
        inside, outside = SpatialValidator._coverage_areas(footprint, coverage)
        tolerance = layer.area_tolerance_m2
        issues = []

        def add(rule_name, code, message):
            severity = getattr(layer.rules, rule_name)
            if severity is not None:
                issues.append(
                    ValidationIssue(
                        severity=severity,
                        code=code,
                        message=message,
                        layer_name=layer.name,
                        subject_id=subject_id,
                        category="spatial",
                        scope=layer.scope,
                        rule_id=f"{layer.name}.{rule_name}",
                        tags=layer.tags,
                    )
                )

        # Positive-area overlap, including full containment; boundary touches do not qualify.
        if inside <= tolerance:
            add(
                "no_overlap",
                "SPATIAL_NO_OVERLAP",
                f"{subject} has no overlap above tolerance with {layer.name!r}.",
            )
        else:
            add(
                "overlap",
                "SPATIAL_OVERLAP",
                f"{subject} overlaps {layer.name!r} by {inside:.6f} m2.",
            )
            if outside > tolerance:
                add(
                    "partial_outside",
                    "SPATIAL_PARTIALLY_OUTSIDE",
                    f"{subject} has {outside:.6f} m2 ({outside / footprint.area:.2%}) "
                    f"outside {layer.name!r}.",
                )

        if layer.rules.multiple_units is not None:
            areas = candidates.geometry.intersection(footprint).area
            ids = candidates.loc[areas > tolerance, layer.id_field].tolist()
            if len(ids) > 1:
                ids.sort(key=lambda value: (type(value).__name__, str(value)))
                add(
                    "multiple_units",
                    "SPATIAL_MULTIPLE_UNITS",
                    f"{subject} occupies {len(ids)} units in {layer.name!r}: {ids!r}.",
                )

        if layer.rules.outside_expected is not None:
            expected = candidates.loc[candidates[layer.id_field].isin(expected_ids)]
            expected_inside, expected_outside = SpatialValidator._coverage_areas(
                footprint,
                expected.geometry.union_all(),
            )
            if expected_inside <= 0 or expected_outside > tolerance:
                add(
                    "outside_expected",
                    "SPATIAL_OUTSIDE_EXPECTED",
                    f"{subject} has {expected_outside:.6f} m2 "
                    f"({expected_outside / footprint.area:.2%}) outside expected IDs "
                    f"{list(expected_ids)!r} in {layer.name!r}.",
                )
        return issues

    @staticmethod
    def _coverage_areas(footprint, coverage):
        if coverage.covers(footprint):
            return float(footprint.area), 0.0
        return float(footprint.intersection(coverage).area), float(
            footprint.difference(coverage).area
        )

    @staticmethod
    def _check_frame(gdf, *, label, allow_empty=False, require_metric=False):
        try:
            check_polygon_frame(
                gdf, label=label, allow_empty=allow_empty, require_metric=require_metric
            )
        except (SpatialDataError, DataCRSError, SpatialGeometryError) as exc:
            raise SpatialValidationError(str(exc)) from exc
