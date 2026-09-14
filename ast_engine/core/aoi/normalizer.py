from __future__ import annotations

import logging

import geopandas as gpd
from geopandas.array import GeometryDtype
from pyproj import CRS
from shapely.geometry import (
    GeometryCollection,
    MultiLineString,
    MultiPoint,
    MultiPolygon,
    Polygon,
)
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union
from shapely.validation import make_valid

from .normalization_reporter import AOINormalizationReportBuilder
from .exceptions import (
    AOINormalizationError,
    AOIRequestError,
    DataCRSError,
    SpatialDataError,
    SpatialGeometryError,
)
from .models import AOIRequest, NormalizedAOI
from .utils import check_gdf, parse_crs, has_area_overlaps
from .constants import DEFAULT_GEOM_FIELD


logger = logging.getLogger(__name__)


class AOINormalizer:
    """
    Cleans raw AOI geometry and applies AOI normalization policy.

    Stage contract:
    - Raw input may be messy but must be a usable GeoDataFrame.
    - Cleaning removes null/empty geometry, repairs invalid geometry, and extracts polygonal geometry.
    - Cleaned AOI is reprojected to the request target CRS.
    - Policy is applied to produce the normalized AOI.
    - Final normalized AOI must be strict, projected, valid, polygonal geometry.
    """

    def normalize_aoi(
        self,
        gdf: gpd.GeoDataFrame,
        request: AOIRequest,
    ) -> NormalizedAOI:
        """
        Normalize a raw AOI GeoDataFrame into a downstream-ready AOI.

        Expected lower-level spatial, CRS, geometry, and request errors are wrapped
        as AOINormalizationError so callers know the normalization stage failed.
        Unexpected programming/system errors are allowed to bubble up to the builder.
        """
        try:
            check_gdf(
                gdf,
                req_projected_crs=False,
                strict=False,
                context="Raw AOI input",
            )

            reporter = AOINormalizationReportBuilder.from_input_gdf(gdf)

            work_gdf = self._clean_geometry(
                gdf,
                reporter=reporter,
            )

            work_gdf = self._conform_target_crs(
                work_gdf,
                target_crs=request.target_crs,
                reporter=reporter,
                require_projected=True,
            )

            check_gdf(
                work_gdf,
                req_projected_crs=True,
                strict=True,
                context="Cleaned AOI before policy",
            )

            normalized_gdf = self._apply_aoi_policy(
                work_gdf,
                request=request,
                reporter=reporter,
            )

            check_gdf(
                normalized_gdf,
                req_projected_crs=True,
                strict=True,
                context="Normalized AOI",
            )

            report = reporter.build(normalized_gdf)

            reporter.log_summary(
                aoi_id=request.aoi_id,
                report=report,
            )

            return NormalizedAOI(
                gdf=normalized_gdf,
                report=report,
            )

        except AOINormalizationError:
            raise

        except (
            SpatialDataError,
            SpatialGeometryError,
            DataCRSError,
            AOIRequestError,
        ) as exc:
            raise AOINormalizationError(
                f"AOI normalization failed for {request.aoi_id!r}: {exc}"
            ) from exc

    def _clean_geometry(
        self,
        gdf: gpd.GeoDataFrame,
        *,
        reporter: AOINormalizationReportBuilder,
    ) -> gpd.GeoDataFrame:
        """
        Remove unusable geometry, repair invalid geometry, and extract polygonal parts only.
        """
        work = gdf.copy()
        geometry_column = work.geometry.name

        # Identify secondary geometry columns by dtype, not by their names.
        secondary_geometry_columns = [
            column
            for column, dtype in work.dtypes.items()
            if column != geometry_column
            and isinstance(dtype, GeometryDtype)
        ]

        if secondary_geometry_columns:
            work.drop(
                columns=secondary_geometry_columns,
                inplace=True,
            )

            reporter.add_note(
                "Removed secondary geometry columns: "
                f"{secondary_geometry_columns!r}."
            )

        # Standardize the retained active geometry column.
        if geometry_column != DEFAULT_GEOM_FIELD:
            if DEFAULT_GEOM_FIELD in work.columns:
                raise SpatialDataError(
                    f"Cannot rename active geometry column {geometry_column!r} "
                    f"to {DEFAULT_GEOM_FIELD!r}: another column already "
                    "uses that name."
                )

            work.rename_geometry(
                DEFAULT_GEOM_FIELD,
                inplace=True,
            )

            reporter.add_note(
                f"Active geometry column renamed from {geometry_column!r} "
                f"to {DEFAULT_GEOM_FIELD!r}."
            )

        before = len(work)
        work = work.loc[
            ~work.geometry.isna()
            & ~work.geometry.is_empty
        ].copy()

        reporter.add_null_empty_removed(before - len(work))

        if work.empty:
            raise SpatialGeometryError(
                "Raw AOI input has no non-null, non-empty geometry."
            )

        reporter.set_repair_input_feature_count(len(work))

        polygonal_geometries: list[Polygon | MultiPolygon | None] = []

        for geom in work.geometry:
            was_invalid = not geom.is_valid
            fixed = geom if not was_invalid else make_valid(geom)

            if was_invalid:
                reporter.add_repaired_feature()

            polygonal, component_counts = self._extract_polygonal(fixed)

            reporter.add_polygon_extraction_counts(component_counts)

            polygonal_geometries.append(polygonal)

        new_geometry = gpd.GeoSeries(
            polygonal_geometries,
            index=work.index,
            crs=work.crs,
            name=work.geometry.name,
        )

        work = work.set_geometry(new_geometry)

        before = len(work)
        work = work.loc[
            ~work.geometry.isna()
            & ~work.geometry.is_empty
        ].copy()

        reporter.add_null_empty_removed(before - len(work))

        if work.empty:
            raise SpatialGeometryError(
                "AOI input has no polygonal geometry after repair/extraction."
            )

        reporter.set_cleaned_feature_count(len(work))

        return work.reset_index(drop=True)

    def _conform_target_crs(
        self,
        gdf: gpd.GeoDataFrame,
        target_crs: str | int | CRS | None,
        *,
        reporter: AOINormalizationReportBuilder,
        require_projected: bool = True,
    ) -> gpd.GeoDataFrame:
        """
        Reproject cleaned AOI geometry to the requested target CRS.
        """
        if gdf.crs is None:
            raise DataCRSError("AOI has no CRS and cannot be reprojected.")

        if target_crs is None:
            raise AOIRequestError("AOI request must contain a target CRS.")

        requested_crs = parse_crs(
            target_crs,
            label="target AOI CRS",
        )

        if require_projected and not requested_crs.is_projected:
            raise DataCRSError(
                "AOI request target CRS must be projected. "
                f"Got: {requested_crs.to_string()}."
            )

        if require_projected and not requested_crs.axis_info[0].unit_name in {
                "metre",
                "meter",
            }:
            raise DataCRSError(
                "AOI request target CRS must have meter units. "
                f"Got: {requested_crs.axis_info[0].unit_name}."
            )

        current_crs = parse_crs(
            gdf.crs,
            label="input AOI CRS",
        )

        if current_crs.equals(requested_crs):
            return gdf

        out = gdf.to_crs(requested_crs)

        reporter.mark_reprojected(
            from_crs=current_crs.to_string(),
            to_crs=requested_crs.to_string(),
        )

        return out

    def _apply_aoi_policy(
        self,
        gdf: gpd.GeoDataFrame,
        *,
        request: AOIRequest,
        reporter: AOINormalizationReportBuilder,
    ) -> gpd.GeoDataFrame:
        """
        Apply request dissolve/overlap policy to cleaned AOI geometry.
        """
        overlaps_before = has_area_overlaps(gdf)

        reporter.set_policy_input(
            request=request,
            input_feature_count=len(gdf),
            overlaps_before=overlaps_before,
        )

        mode = request.dissolve_mode

        if mode == "full_union":
            out = self._apply_full_union_policy(gdf)

        elif mode == "by_fields":
            out = self._apply_by_fields_policy(
                gdf,
                dissolve_fields=tuple(request.dissolve_fields),
            )

        elif mode == "preserve_features":
            out = gdf.copy()

        else:
            raise AOIRequestError(f"Unsupported dissolve_mode: {mode!r}.")

        out = out.reset_index(drop=True)

        overlaps_after = has_area_overlaps(out)

        reporter.set_policy_output(
            output_feature_count=len(out),
            overlaps_after=overlaps_after,
        )

        if not request.allow_overlaps and overlaps_after:
            raise SpatialGeometryError(
                "AOI policy output contains overlapping polygons, "
                "but allow_overlaps=False."
            )

        return out

    def _apply_full_union_policy(
        self,
        gdf: gpd.GeoDataFrame,
    ) -> gpd.GeoDataFrame:
        geom = gdf.union_all()

        if geom is None or geom.is_empty:
            raise SpatialGeometryError(
                "AOI full_union policy produced empty geometry."
            )

        if geom.geom_type not in {"Polygon", "MultiPolygon"}:
            raise SpatialGeometryError(
                "AOI full_union policy produced non-polygonal geometry: "
                f"{geom.geom_type!r}."
            )

        return gpd.GeoDataFrame(
            {DEFAULT_GEOM_FIELD: [geom]},
            geometry=DEFAULT_GEOM_FIELD,
            crs=gdf.crs,
        )

    def _apply_by_fields_policy(
        self,
        gdf: gpd.GeoDataFrame,
        *,
        dissolve_fields: tuple[str, ...],
    ) -> gpd.GeoDataFrame:
        if not dissolve_fields:
            raise AOIRequestError(
                "dissolve_mode='by_fields' requires dissolve_fields."
            )

        missing = [
            field
            for field in dissolve_fields
            if field not in gdf.columns
        ]

        if missing:
            raise SpatialDataError(
                f"AOI data is missing dissolve field(s): {missing}."
            )

        geometry_column = gdf.geometry.name

        if geometry_column in dissolve_fields:
            raise AOIRequestError(
                "The active geometry column cannot be a dissolve field."
            )

        columns = [*dissolve_fields, geometry_column]

        return gdf.loc[:, columns].dissolve(
            by=list(dissolve_fields),
            as_index=False,
            dropna=False,
        )


    def _extract_polygonal(
        self,
        geom: BaseGeometry | None,
    ) -> tuple[Polygon | MultiPolygon | None, dict[str, int]]:
        """
        Extract polygons from nested collections and multipart geometries.

        Counts describe non-empty individual components before union:
        - each Polygon counts as one retained component;
        - each non-polygon component counts as one discarded component;
        - collections themselves are not counted;
        - None and empty geometries are ignored.

        Geometry repair is handled by the caller before extraction.
        """
        meta = {
            "input_component_count": 0,
            "polygon_component_count": 0,
            "nonpolygon_component_drop_count": 0,
        }
        polygon_parts: list[Polygon] = []

        def collect(part: BaseGeometry | None) -> None:
            if part is None or part.is_empty:
                return

            # Inspect every member, including further nested collections.
            if isinstance(
                part,
                (
                    GeometryCollection,
                    MultiPolygon,
                    MultiLineString,
                    MultiPoint,
                ),
            ):
                for child in part.geoms:
                    collect(child)
                return

            meta["input_component_count"] += 1

            if isinstance(part, Polygon):
                polygon_parts.append(part)
                meta["polygon_component_count"] += 1
            else:
                meta["nonpolygon_component_drop_count"] += 1

        collect(geom)

        if not polygon_parts:
            return None, meta

        if len(polygon_parts) == 1:
            return polygon_parts[0], meta

        # Union once, after collecting all polygon components.
        merged = unary_union(polygon_parts)

        if merged.is_empty or not isinstance(merged, (Polygon, MultiPolygon)):
            raise SpatialGeometryError(
                "Polygon extraction produced an unexpected "
                "empty or non-polygonal result."
            )

        return merged, meta