from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Any, Optional, Tuple
import geopandas as gpd


# ============================================================
# AOI Request model
# ============================================================

@dataclass(frozen=True)
class AOIRequest:
    """
    AOI request schema to be consumed by the builder.
    - This schema represents the input parameters for building an AOI, and any relevant metadata or policy controls.
    - The builder will take this request object and process it through normalization, inspection, and validation
    """
    aoi_id: str
    name: str
    target_crs: str = "EPSG:3005"

    # AOI policy controls
    dissolve_mode: Literal["full_union", "by_fields", "preserve_features"] = "full_union"
    dissolve_fields: tuple[str, ...] = field(default_factory=tuple)
    allow_overlaps: bool = False


# ============================================================
# Area of Interest models
# ============================================================

@dataclass
class AreaOfInterest:
    aoi_id: str
    name: str
    gdf: gpd.GeoDataFrame
    normalization_report: dict[str, Any]
    properties: AOIProperties
    validation: AOIValidationResult
    parts: tuple[AOIPart, ...] = field(default_factory=tuple)



    def __post_init__(self) -> None:
        if self.gdf.crs is None:
            raise ValueError(f"AOI {self.aoi_id} has no CRS defined")

    # Convenience properties pulled from immutable AOIProperties
    @property
    def crs_epsg(self) -> int:
        return self.properties.crs_epsg

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        return self.properties.bounds

    @property
    def footprint_area_ha(self) -> float:
        return self.properties.footprint_area_ha
    
    @property
    def overlay_area_ha(self) -> float:
        return self.properties.overlay_area_ha
    

@dataclass(frozen=True)
class AOIProperties:
    crs_epsg: int
    footprint_area_ha: float
    bounds: tuple[float, float, float, float]

    part_count: int
    overlay_area_ha: float


# ============================================================
# Area of Interest parts models
# ============================================================

@dataclass(frozen=True)
class AOIPart:
    part_id: str
    parent_aoi_id: str
    geom_type: str
    part_index: int
    gdf: gpd.GeoDataFrame
    bounds: tuple[float, float, float, float]
    area_ha: float


# ============================================================
# Normalization results models
# ============================================================

@dataclass
class AOINormalizationReport:
    # Input / output summary
    input_feature_count: int
    cleaned_feature_count: int = 0
    output_feature_count: int = 0

    input_crs: Optional[str] = None
    output_crs: Optional[str] = None

    # Cleaning actions
    null_or_empty_removed_count: int = 0
    repair_input_feature_count: int = 0
    repaired_feature_count: int = 0
    polygon_extract_input_feature_count: int = 0
    polygon_extract_output_feature_count: int = 0
    polygon_extract_drop_count: int = 0

    # Policy settings used
    policy_name: str = "full_union"
    dissolve_fields_used: tuple[str, ...] = field(default_factory=tuple)
    allow_overlaps: bool = False
    policy_applied: bool = False

    # Policy effects
    policy_input_feature_count: int = 0
    policy_output_feature_count: int = 0
    overlaps_detected_before_policy: bool = False
    overlaps_present_after_policy: bool = False
    overlaps_resolved_by_policy: bool = False

    # CRS actions
    was_reprojected: bool = False

    # Notes for validator / reporting
    notes: tuple[str, ...] = field(default_factory=tuple)


@dataclass
class NormalizedAOI:
    gdf: gpd.GeoDataFrame
    report: AOINormalizationReport


# ============================================================
# Validation results models
# ============================================================

@dataclass(frozen=True)
class ValidationIssue:
    severity: str
    code: str
    message: str


@dataclass(frozen=True)
class AOIValidationResult:
    is_valid: bool
    issues: tuple[ValidationIssue, ...] = field(default_factory=tuple)