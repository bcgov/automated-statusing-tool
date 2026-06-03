from __future__ import annotations

from dataclasses import dataclass, field
import geopandas as gpd

from .models import AOIProperties, AOINormalizationReport, AOIPart, AOIValidationResult, ValidationIssue
from .inspector import AOIProperties
from .normalizer import AOINormalizationReport

SLIVER_THRESHOLD = 0.1 # Minimum area in hectares for a part to be considered valid (e.g. to filter out slivers from processing)
LARGE_AREA_THRESHOLD = 10_000 # Area in hectares above which a part is flagged for review (e.g. to identify parts that may need to be split for reporting or processing)


class AOIValidator:
    """
    Validates the AreaOfInterest object and its derived parts.
    Ensures that the AOI meets all necessary criteria for processing and reporting.
        - Validation is separate from inspection to allow for more complex rules that may depend on multiple properties or parts.
        - Validation issues are categorized by severity (e.g. error, warning) to allow for flexible handling in the future.
        - The validator can be extended with additional rules as needed without affecting the core building and inspection logic.
        - The validation result can be included in the final AOI object for downstream use in reporting or user feedback.
        - This design allows for a clear separation of concerns and makes the validation logic more maintainable and testable.
        - The validator can also be used independently of the builder if needed, for example to validate AOIs that were built through other means or to re-validate AOIs after certain transformations.
        - Overall, this approach provides a robust framework for ensuring the integrity and quality of AOIs throughout the processing pipeline.
    """

    def validate(
        self,
        *,
        gdf: gpd.GeoDataFrame,
        report: AOINormalizationReport,
        parts: tuple[AOIPart, ...],
        properties: AOIProperties,
    ) -> AOIValidationResult:
        issues: list[ValidationIssue] = []

        # Validate AOI object for required properties
        if gdf.empty:
            issues.append(
                ValidationIssue("error", "NO_GDF", "AOI has no Geopandas GeoDataFrame")
            )
        if not properties:
            issues.append(
                ValidationIssue("error", "NO_PROPERTIES", "AOI has no properties")
            )

        if not parts:
            issues.append(
                ValidationIssue("error", "NO_PARTS", "AOI has no parts")
            )

        ##### VALIDATE AGAINST NORMALIZATION REPORT #####
        if not report:
            issues.append(
                ValidationIssue("error", "NO_NORMALIZATION_REPORT", "AOI has no normalization report")
            )

        if not report.allow_overlaps and report.overlaps_present_after_policy:
            issues.append(
                ValidationIssue(
                    "error",
                    "OVERLAPS_PRESENT",
                    "Overlapping AOI polygons remain after policy but are not allowed.",
                )
            )

        if report.null_or_empty_removed_count > 0 or report.polygon_extract_drop_count > 0:
            issues.append(
                ValidationIssue(
                    "warning",
                    "NULL_OR_NON_POLYGONS_REMOVED",
                    "Null or non-polygonal features were removed during normalization.",
                )
            )

        ## TODO: Continue to check normalization report for specific issues that should be elevated to validation issues

        ###################################################

        # Geometry issues
        if not gdf.geometry.is_valid.all():
            issues.append(
                ValidationIssue("error", "INVALID_GEOMETRY", "AOI contains invalid geometry")
            )

        if properties.footprint_area_ha <= 0 or properties.overlay_area_ha <= 0:
            issues.append(
                ValidationIssue("error", "ZERO_AREA", "AOI area is zero or negative")
            )

        # Validate AOI parts
        if properties.part_count != len(parts):
            issues.append(
                ValidationIssue(
                    "error",
                    "PART_COUNT_MISMATCH",
                    f"AOI part_count={properties.part_count} but built {len(parts)} parts",
                )
            )

        for part in parts:
            if part.area_ha <= SLIVER_THRESHOLD:
                issues.append(
                    ValidationIssue(
                        "error",
                        "ZERO_AREA_OR_SLIVER_PART",
                        f"AOI part {part.part_id} area is zero, negative or less than the sliver threshold",
                    )
                )

            if part.area_ha >= LARGE_AREA_THRESHOLD:
                issues.append(
                    ValidationIssue(
                        "error",
                        "LARGE_PART",
                        f"AOI part {part.part_id} is {part.area_ha} hectares and exceeds "
                        f"the large area threshold of {LARGE_AREA_THRESHOLD} hectares. "
                        f"Consider reviewing for potential splitting",
                    )
                )
                
            ##### VALIDATE FOR COMPLEX GEOMETRIES OF AOI PARTS #####
            ## TODO: Validate number of vertices for each part
            ## TODO: Validate for other complexities like holes (donuts) for each part


            ##### VALIDATE SPATIAL LOCATION of AOI parts #####
            ## TODO: Validate if AOI part crosses REGIONAL BOUNDARY - Warn
            ## TODO: Validate if AOI part outside expected REGIONAL BOUNDARY - Error
            ## TODO: Validate if AOI part crosses BC bounds - Warn
            ## TODO: Validate if AOI part not contained by BC bounds - Error


        return AOIValidationResult(
            is_valid=not any(i.severity == "error" for i in issues),
            issues=tuple(issues),
        )