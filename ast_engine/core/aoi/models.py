from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Any, cast, get_args
from pyproj import CRS
import geopandas as gpd
from shapely.geometry.base import BaseGeometry

from .exceptions import AOIRequestError, DataCRSError, SpatialDataError, SpatialGeometryError, AOIPartBuildError
from .utils import count_vertices, has_m, has_z


# ============================================================
# AOI Request model
# ============================================================

DissolveMode = Literal[
    "full_union",
    "by_fields",
    "preserve_features",
]

SUPPORTED_DISSOLVE_MODES: frozenset[str] = frozenset(
    get_args(DissolveMode)
)


@dataclass(frozen=True)
class AOIRequest:
    aoi_id: str
    name: str
    target_crs: str = "EPSG:3005"

    dissolve_mode: DissolveMode = "full_union"
    dissolve_fields: tuple[str, ...] = field(default_factory=tuple)
    allow_overlaps: bool = False

    _target_crs_obj: CRS = field(
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        # Validate scalar input types before normalizing them.
        if not isinstance(self.aoi_id, str):
            raise AOIRequestError(
                "AOIRequest.aoi_id must be a string."
            )

        if not isinstance(self.name, str):
            raise AOIRequestError(
                "AOIRequest.name must be a string."
            )

        if not isinstance(self.dissolve_mode, str):
            raise AOIRequestError(
                "AOIRequest.dissolve_mode must be a string."
            )

        if not isinstance(self.dissolve_fields, (tuple, list)):
            raise AOIRequestError(
                "AOIRequest.dissolve_fields must be a sequence of strings."
            )

        if not all(
            isinstance(field_name, str)
            for field_name in self.dissolve_fields
        ):
            raise AOIRequestError(
                "AOIRequest.dissolve_fields must contain only strings."
            )

        if not isinstance(self.target_crs, str):
            raise AOIRequestError(
                "AOIRequest.target_crs must be a string."
            )

        if not isinstance(self.allow_overlaps, bool):
            raise AOIRequestError(
                "AOIRequest.allow_overlaps must be a boolean."
            )

        # Normalize values.
        aoi_id = self.aoi_id.strip()
        name = self.name.strip()
        dissolve_mode = self.dissolve_mode.strip().lower()
        dissolve_fields = tuple(
            field_name.strip()
            for field_name in self.dissolve_fields
            if field_name.strip()
        )

        if not aoi_id:
            raise AOIRequestError(
                "AOIRequest.aoi_id cannot be empty."
            )

        if not name:
            raise AOIRequestError(
                "AOIRequest.name cannot be empty."
            )

        if dissolve_mode not in SUPPORTED_DISSOLVE_MODES:
            raise AOIRequestError(
                f"Unsupported AOIRequest.dissolve_mode: "
                f"{self.dissolve_mode!r}. Expected one of: "
                f"{sorted(SUPPORTED_DISSOLVE_MODES)}."
            )

        if dissolve_mode == "by_fields" and not dissolve_fields:
            raise AOIRequestError(
                "AOIRequest.dissolve_fields must be provided when "
                "dissolve_mode='by_fields'."
            )

        if dissolve_mode != "by_fields" and dissolve_fields:
            raise AOIRequestError(
                "AOIRequest.dissolve_fields should only be provided when "
                "dissolve_mode='by_fields'."
            )

        if len(set(self.dissolve_fields)) != len(self.dissolve_fields):
            raise AOIRequestError(
                "AOIRequest.dissolve_fields cannot contain duplicates."
            )

        try:
            crs = CRS.from_user_input(self.target_crs)
        except Exception as exc:
            raise AOIRequestError(
                f"Invalid AOIRequest.target_crs: {self.target_crs!r}."
            ) from exc

        if not crs.is_projected:
            raise AOIRequestError(
                "AOIRequest.target_crs must be projected. "
                f"Received: {self.target_crs!r}."
            )

        object.__setattr__(self, "aoi_id", aoi_id)
        object.__setattr__(self, "name", name)
        object.__setattr__(
            self,
            "dissolve_mode",
            cast(DissolveMode, dissolve_mode),
        )
        object.__setattr__(
            self,
            "dissolve_fields",
            dissolve_fields,
        )
        object.__setattr__(self, "_target_crs_obj", crs)

    @property
    def target_crs_obj(self) -> CRS:
        return self._target_crs_obj

    @property
    def target_epsg(self) -> int | None:
        return self.target_crs_obj.to_epsg()

    @property
    def is_projected(self) -> bool:
        return self.target_crs_obj.is_projected
    

@dataclass(frozen=True)
class AOIBuildRequest:
    """
    Full request object passed to AOIBuilder.

    Contains the AOI build specification and raw AOI geometry.
    Validation configuration/context is supplied through the AOIValidator,
    not through this request.
    """

    spec: AOIRequest
    raw_gdf: gpd.GeoDataFrame

    def __post_init__(self) -> None:
        if self.spec is None:
            raise AOIRequestError("AOIBuildRequest.spec cannot be None")

        if self.raw_gdf is None:
            raise AOIRequestError("AOIBuildRequest.raw_gdf cannot be None")


# ============================================================
# Area of Interest models
# ============================================================

@dataclass
class AreaOfInterest:
    aoi_id: str
    name: str
    gdf: gpd.GeoDataFrame
    properties: AOIProperties
    parts: tuple[AOIPart, ...] = field(default_factory=tuple)


    def __post_init__(self) -> None:
        if self.gdf.crs is None:
            raise DataCRSError(f"AOI {self.aoi_id} has no CRS defined")

    # Convenience properties pulled from immutable AOIProperties
    @property
    def crs_epsg(self) -> int | None:
        return self.properties.crs_epsg

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        return self.properties.bounds

    @property
    def footprint_area_ha(self) -> float:
        return self.properties.footprint_area_ha
    
    @property
    def parts_area_ha(self) -> float:
        return self.properties.parts_area_ha
    
    @property
    def part_count(self) -> int:
        return self.properties.part_count
    

@dataclass(frozen=True)
class AOIProperties:
    crs_epsg: int | None
    crs_string: str

    footprint_area_ha: float
    bounds: tuple[float, float, float, float]

    part_count: int
    parts_area_ha: float

    feature_count: int
    geometry_type: str

    parts_to_footprint_ratio: float
    vertex_count: int
    max_vertices_per_part: int

    has_z: bool
    has_m: bool


# ============================================================
# Area of Interest parts models
# ============================================================

@dataclass(frozen=True)
class AOIPart:
    """
    Single AOI analysis part.

    Each AOIPart stores a one-row GeoDataFrame plus derived part-level
    spatial properties used by the AOI inspector and validator.
    """

    part_id: str
    parent_aoi_id: str
    geom_type: str
    part_index: int
    gdf: gpd.GeoDataFrame
    bounds: tuple[float, float, float, float]
    area_ha: float
    vertex_count: int
    has_z: bool
    has_m: bool

    @classmethod
    def from_gdf(
        cls,
        *,
        parent_aoi_id: str,
        part_index: int,
        gdf: gpd.GeoDataFrame,
        part_id: str,
    ) -> AOIPart:
        if gdf.empty:
            raise SpatialDataError("Cannot build AOIPart from empty GeoDataFrame.")

        if len(gdf) != 1:
            raise AOIPartBuildError(
                f"AOIPart must be built from a one-row GeoDataFrame. Got {len(gdf)} rows."
            )

        geom = gdf.geometry.iloc[0]

        if geom is None or geom.is_empty:
            raise SpatialGeometryError("Cannot build AOIPart from null or empty geometry.")

        resolved_part_id = part_id or f"{parent_aoi_id}_part_{part_index:04d}"

        return cls(
            part_id=resolved_part_id,
            parent_aoi_id=parent_aoi_id,
            geom_type=str(geom.geom_type),
            part_index=int(part_index),
            gdf=gdf.reset_index(drop=True),
            bounds=tuple(float(value) for value in geom.bounds),
            area_ha=float(geom.area / 10_000.0),
            vertex_count=count_vertices(geom),
            has_z=has_z(geom),
            has_m=has_m(geom),
        )

    @property
    def geometry(self) -> BaseGeometry:
        """
        Return the single Shapely geometry for this AOI part.
        """
        if self.gdf.empty:
            raise ValueError(
                f"AOIPart {self.part_id!r} has an empty GeoDataFrame."
            )

        return self.gdf.geometry.iloc[0]

    @property
    def crs(self) -> Any:
        """
        Return the CRS of the part GeoDataFrame.
        """
        return self.gdf.crs


# ============================================================
# Normalization results models
# ============================================================

@dataclass(frozen=True)
class AOINormalizationReport:
    # Input / output summary
    input_feature_count: int
    cleaned_feature_count: int
    output_feature_count: int

    input_crs: str
    output_crs: str

    # Cleaning actions
    null_or_empty_removed_count: int
    repair_input_feature_count: int
    repaired_feature_count: int
    polygon_extract_input_feature_count: int
    polygon_extract_output_feature_count: int
    polygon_extract_drop_count: int

    # Policy settings used
    policy_name: str
    dissolve_fields_used: tuple[str, ...]
    allow_overlaps: bool
    policy_applied: bool

    # Policy effects
    policy_input_feature_count: int
    policy_output_feature_count: int
    overlaps_detected_before_policy: bool
    overlaps_present_after_policy: bool
    overlaps_resolved_by_policy: bool

    # CRS actions
    was_reprojected: bool

    # Notes for validator / reporting
    notes: tuple[str, ...] = field(default_factory=tuple)


@dataclass
class NormalizedAOI:
    gdf: gpd.GeoDataFrame
    report: AOINormalizationReport


# ============================================================
# Validation results models
# ============================================================
ValidationSeverity = Literal["error", "warning", "info"]

@dataclass(frozen=True)
class ValidationIssue:
    severity: ValidationSeverity
    code: str
    message: str

    def __post_init__(self) -> None:
        severity = self.severity.strip().lower()
        code = self.code.strip().upper()

        allowed = {"error", "warning", "info"}

        if severity not in allowed:
            raise ValueError(
                f"Invalid validation severity: {self.severity!r}. "
                f"Expected one of: {sorted(allowed)}"
            )

        if not code:
            raise ValueError("ValidationIssue.code cannot be empty")

        if not self.message.strip():
            raise ValueError("ValidationIssue.message cannot be empty")

        object.__setattr__(self, "severity", severity)
        object.__setattr__(self, "code", code)
        object.__setattr__(self, "message", self.message.strip())


@dataclass(frozen=True)
class AOIValidationResult:
    issues: tuple[ValidationIssue, ...] = field(default_factory=tuple)

    @property
    def is_valid(self) -> bool:
        return not self.has_errors

    @property
    def has_errors(self) -> bool:
        return any(i.severity == "error" for i in self.issues)

    @property
    def has_warnings(self) -> bool:
        return any(i.severity == "warning" for i in self.issues)

    @property
    def errors(self) -> tuple[ValidationIssue, ...]:
        return tuple(i for i in self.issues if i.severity == "error")

    @property
    def warnings(self) -> tuple[ValidationIssue, ...]:
        return tuple(i for i in self.issues if i.severity == "warning")

    @property
    def infos(self) -> tuple[ValidationIssue, ...]:
        return tuple(i for i in self.issues if i.severity == "info")

# ============================================================
# Validation results models
# ============================================================

@dataclass(frozen=True)
class AOIBuildResult:
    aoi: AreaOfInterest
    validation: AOIValidationResult
    normalization_report: AOINormalizationReport

    @property
    def is_valid(self) -> bool:
        return self.validation.is_valid

    @property
    def has_errors(self) -> bool:
        return self.validation.has_errors

    @property
    def has_warnings(self) -> bool:
        return self.validation.has_warnings

    @property
    def errors(self) -> tuple[ValidationIssue, ...]:
        return self.validation.errors

    @property
    def warnings(self) -> tuple[ValidationIssue, ...]:
        return self.validation.warnings

    @property
    def infos(self) -> tuple[ValidationIssue, ...]:
        return self.validation.infos