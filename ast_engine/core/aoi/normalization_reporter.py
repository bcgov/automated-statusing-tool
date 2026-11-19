from __future__ import annotations

import logging
from typing import Any

import geopandas as gpd

from .exceptions import AOINormalizationError, DataCRSError
from .models import AOIRequest, AOINormalizationReport


logger = logging.getLogger(__name__)

_MISSING = object()


class AOINormalizationReportBuilder:
    """
    Mutable report builder for AOI normalization.

    This class tracks normalization events and builds the final immutable
    AOINormalizationReport.

    The normalizer should call named methods on this builder rather than
    directly mutating a report dictionary.
    """

    def __init__(self, gdf: gpd.GeoDataFrame) -> None:
        self._data: dict[str, Any] = {
            # Input/output summary
            "input_feature_count": len(gdf),
            "cleaned_feature_count": _MISSING,
            "output_feature_count": _MISSING,

            # CRS
            "input_crs": str(gdf.crs) if gdf.crs else _MISSING,
            "output_crs": _MISSING,
            "was_reprojected": False,

            # Geometry cleanup
            "null_or_empty_removed_count": 0,
            "repair_input_feature_count": _MISSING,
            "repaired_feature_count": 0,
            "polygon_extract_input_feature_count": 0,
            "polygon_extract_output_feature_count": 0,
            "polygon_extract_drop_count": 0,

            # Policy settings
            "policy_name": _MISSING,
            "dissolve_fields_used": _MISSING,
            "allow_overlaps": _MISSING,
            "policy_applied": False,

            # Policy effects
            "policy_input_feature_count": _MISSING,
            "policy_output_feature_count": _MISSING,
            "overlaps_detected_before_policy": _MISSING,
            "overlaps_present_after_policy": _MISSING,
            "overlaps_resolved_by_policy": _MISSING,

            # Notes
            "notes": [],
        }

    @classmethod
    def from_input_gdf(
        cls,
        gdf: gpd.GeoDataFrame,
    ) -> AOINormalizationReportBuilder:
        return cls(gdf)

    def add_null_empty_removed(
        self,
        count: int,
    ) -> None:
        self._data["null_or_empty_removed_count"] += int(count)

    def set_repair_input_feature_count(
        self,
        count: int,
    ) -> None:
        self._data["repair_input_feature_count"] = int(count)

    def add_repaired_feature(
        self,
    ) -> None:
        self._data["repaired_feature_count"] += 1

    def add_polygon_extraction_counts(
        self,
        counts: dict[str, int],
    ) -> None:
        self._data["polygon_extract_input_feature_count"] += int(
            counts["input_component_count"]
        )
        self._data["polygon_extract_output_feature_count"] += int(
            counts["polygon_component_count"]
        )
        self._data["polygon_extract_drop_count"] += int(
            counts["nonpolygon_component_drop_count"]
        )

    def set_cleaned_feature_count(
        self,
        count: int,
    ) -> None:
        self._data["cleaned_feature_count"] = int(count)

    def mark_reprojected(
        self,
        *,
        from_crs: str,
        to_crs: str,
    ) -> None:
        self._data["was_reprojected"] = True
        self.add_note(
            f"AOI reprojected from {from_crs} to {to_crs}."
        )

    def add_note(
        self,
        note: str,
    ) -> None:
        self._data["notes"].append(note)

    def set_policy_input(
        self,
        *,
        request: AOIRequest,
        input_feature_count: int,
        overlaps_before: bool,
    ) -> None:
        self._data["policy_name"] = request.dissolve_mode
        self._data["dissolve_fields_used"] = tuple(request.dissolve_fields)
        self._data["allow_overlaps"] = bool(request.allow_overlaps)
        self._data["policy_input_feature_count"] = int(input_feature_count)
        self._data["overlaps_detected_before_policy"] = bool(overlaps_before)

    def set_policy_output(
        self,
        *,
        output_feature_count: int,
        overlaps_after: bool,
    ) -> None:
        overlaps_before = self._require("overlaps_detected_before_policy")

        self._data["policy_output_feature_count"] = int(output_feature_count)
        self._data["overlaps_present_after_policy"] = bool(overlaps_after)
        self._data["overlaps_resolved_by_policy"] = (
            bool(overlaps_before) and not bool(overlaps_after)
        )
        self._data["policy_applied"] = True

    @property
    def overlaps_present_after_policy(self) -> bool:
        return bool(self._require("overlaps_present_after_policy"))

    def build(
        self,
        gdf: gpd.GeoDataFrame,
    ) -> AOINormalizationReport:
        output_crs = str(gdf.crs) if gdf.crs else None

        if output_crs is None:
            raise DataCRSError(
                "Normalization report cannot be built because output CRS is missing."
            )

        self._data["output_feature_count"] = len(gdf)
        self._data["output_crs"] = output_crs

        return AOINormalizationReport(
            input_feature_count=self._require("input_feature_count"),
            cleaned_feature_count=self._require("cleaned_feature_count"),
            output_feature_count=self._require("output_feature_count"),

            input_crs=self._require("input_crs"),
            output_crs=self._require("output_crs"),

            null_or_empty_removed_count=self._require(
                "null_or_empty_removed_count"
            ),
            repair_input_feature_count=self._require(
                "repair_input_feature_count"
            ),
            repaired_feature_count=self._require("repaired_feature_count"),
            polygon_extract_input_feature_count=self._require(
                "polygon_extract_input_feature_count"
            ),
            polygon_extract_output_feature_count=self._require(
                "polygon_extract_output_feature_count"
            ),
            polygon_extract_drop_count=self._require(
                "polygon_extract_drop_count"
            ),

            policy_name=self._require("policy_name"),
            dissolve_fields_used=tuple(
                self._require("dissolve_fields_used")
            ),
            allow_overlaps=self._require("allow_overlaps"),
            policy_applied=self._require("policy_applied"),

            policy_input_feature_count=self._require(
                "policy_input_feature_count"
            ),
            policy_output_feature_count=self._require(
                "policy_output_feature_count"
            ),
            overlaps_detected_before_policy=self._require(
                "overlaps_detected_before_policy"
            ),
            overlaps_present_after_policy=self._require(
                "overlaps_present_after_policy"
            ),
            overlaps_resolved_by_policy=self._require(
                "overlaps_resolved_by_policy"
            ),

            was_reprojected=self._require("was_reprojected"),
            notes=tuple(self._require("notes")),
        )

    def log_summary(
        self,
        *,
        aoi_id: str,
        report: AOINormalizationReport,
    ) -> None:
        logger.debug(
            "AOI normalization summary | aoi_id=%s | "
            "features=%s input -> %s cleaned -> %s output | "
            "crs=%s -> %s | reprojected=%s",
            aoi_id,
            report.input_feature_count,
            report.cleaned_feature_count,
            report.output_feature_count,
            report.input_crs,
            report.output_crs,
            report.was_reprojected,
        )

        logger.debug(
            "AOI normalization geometry cleanup | aoi_id=%s | "
            "null_empty_removed=%s | repaired=%s/%s | "
            "polygon_components_kept=%s | non_polygon_components_dropped=%s",
            aoi_id,
            report.null_or_empty_removed_count,
            report.repaired_feature_count,
            report.repair_input_feature_count,
            report.polygon_extract_output_feature_count,
            report.polygon_extract_drop_count,
        )

        logger.debug(
            "AOI normalization policy | aoi_id=%s | mode=%s | dissolve_fields=%s | "
            "allow_overlaps=%s | policy_features=%s -> %s | "
            "overlaps_before=%s | overlaps_after=%s | overlaps_resolved=%s",
            aoi_id,
            report.policy_name,
            report.dissolve_fields_used,
            report.allow_overlaps,
            report.policy_input_feature_count,
            report.policy_output_feature_count,
            report.overlaps_detected_before_policy,
            report.overlaps_present_after_policy,
            report.overlaps_resolved_by_policy,
        )

    def _require(
        self,
        key: str,
    ) -> Any:
        if key not in self._data:
            raise AOINormalizationError(
                f"Normalization report is missing required key: {key!r}."
            )

        value = self._data[key]

        if value is _MISSING:
            raise AOINormalizationError(
                f"Normalization report value was not set: {key!r}."
            )

        return value