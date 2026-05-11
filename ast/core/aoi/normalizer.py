from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Literal

import geopandas as gpd
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon
from shapely.ops import unary_union
from shapely.validation import make_valid

from .exceptions import AOIValidationError
from .aoi_builder import AOIRequest
from .models import AOINormalizationReport, NormalizedAOI


class AOINormalizer:
    """
    Cleans raw AOI geometry and applies AOI policy.
    """

    def normalize_aoi(
        self,
        gdf: gpd.GeoDataFrame,
        request: AOIRequest,
    ) -> NormalizedAOI:
        cleaned_gdf, report_data = self._clean_geometry(gdf, request.target_crs)
        policy_gdf, report_data = self._apply_aoi_policy(cleaned_gdf, request, report_data)

        report = AOINormalizationReport(
            input_feature_count=report_data["input_feature_count"],
            cleaned_feature_count=report_data["cleaned_feature_count"],
            output_feature_count=len(policy_gdf),
            input_crs=report_data["input_crs"],
            output_crs=str(policy_gdf.crs) if policy_gdf.crs else None,
            null_or_empty_removed_count=report_data["null_or_empty_removed_count"],
            repair_input_feature_count=report_data["repair_input_feature_count"],
            repaired_feature_count=report_data["repaired_feature_count"],
            polygon_extract_input_feature_count=report_data["polygon_extract_input_feature_count"],
            polygon_extract_output_feature_count=report_data["polygon_extract_output_feature_count"],
            polygon_extract_drop_count=report_data["polygon_extract_drop_count"],
            policy_name=report_data["policy_name"],
            dissolve_fields_used=tuple(report_data["dissolve_fields_used"]),
            allow_overlaps=report_data["allow_overlaps"],
            overlaps_detected_before_policy=report_data["overlaps_detected_before_policy"],
            overlaps_present_after_policy=report_data["overlaps_present_after_policy"],
            overlaps_resolved_by_policy=report_data["overlaps_resolved_by_policy"],
            was_reprojected=report_data["was_reprojected"],
            notes=tuple(report_data["notes"]),
        )

        return NormalizedAOI(gdf=policy_gdf, report=report)

    def _clean_geometry(
        self,
        gdf: gpd.GeoDataFrame,
        target_crs: Optional[str],
    ) -> tuple[gpd.GeoDataFrame, dict]:
        if gdf is None:
            raise AOIValidationError("Input AOI GeoDataFrame is None")

        if gdf.empty:
            raise AOIValidationError("Input AOI GeoDataFrame is empty")

        if gdf.crs is None:
            raise AOIValidationError("Input AOI has no CRS")

        if gdf.geometry.name not in gdf.columns:
            raise AOIValidationError("Input AOI has no active geometry column")

        work = gdf.copy()

        report = {
            "input_feature_count": len(work),
            "input_crs": str(work.crs),
            "null_or_empty_removed_count": 0,
            "repair_input_feature_count": 0,
            "repaired_feature_count": 0,
            "polygon_extract_input_feature_count": 0,
            "polygon_extract_output_feature_count": 0,
            "polygon_extract_drop_count": 0,
            "cleaned_feature_count": 0,
            "was_reprojected": False,
            "notes": [],
        }

        # drop null / empty
        before = len(work)
        work = work.loc[~work.geometry.isna() & ~work.geometry.is_empty].copy()
        report["null_or_empty_removed_count"] = before - len(work)

        if work.empty:
            raise AOIValidationError("Input AOI has no non-null, non-empty geometry")

        # repair / extract polygonal
        report["repair_input_feature_count"] = len(work)

        repaired_geoms = []
        for geom in work.geometry:
            was_invalid = not geom.is_valid
            fixed = geom if not was_invalid else make_valid(geom)

            if was_invalid:
                report["repaired_feature_count"] += 1

            polygonal, components = self._extract_polygonal(fixed)

            report["polygon_extract_input_feature_count"] += components["input_component_count"] # Includes any lines, points, etc.
            report["polygon_extract_output_feature_count"] += components["polygon_component_count"] # Only polygns, Multipolygons and GeometryCollections with polygonal geometry.
            report["polygon_extract_drop_count"] += components["nonpolygon_component_drop_count"] # Count of dropped nonpolygon features

            repaired_geoms.append(polygonal)

        work = work.copy()
        work["geometry"] = repaired_geoms # This works if you do not drop rows above. Explicit version may be required for more robustness.
        before_drops = len(work)
        work = work.loc[~work.geometry.isna() & ~work.geometry.is_empty].copy()
        report["null_or_empty_removed_count"] += before_drops - len(work)

        if work.empty:
            raise AOIValidationError("Input AOI has no polygonal geometry after repair")

        # reproject
        if target_crs:
            if work.crs != target_crs:
                work = work.to_crs(target_crs)
                report["was_reprojected"] = True
                report["notes"].append(f"AOI reprojected to {target_crs}")

        report["cleaned_feature_count"] = len(work)

        return work, report

    def _apply_aoi_policy(
        self,
        gdf: gpd.GeoDataFrame,
        request: AOIRequest,
        report: dict,
    ) -> tuple[gpd.GeoDataFrame, dict]:
        report["policy_name"] = request.dissolve_mode
        report["dissolve_fields_used"] = request.dissolve_fields
        report["allow_overlaps"] = request.allow_overlaps
        report["overlaps_detected_before_policy"] = self._has_overlaps(gdf)

        mode = request.dissolve_mode

        if mode == "full_union":
            geom = gdf.union_all()
            if geom is None or geom.is_empty:
                raise AOIValidationError("AOI full_union policy produced empty geometry")
            if geom.geom_type not in {"Polygon", "MultiPolygon"}:
                raise AOIValidationError(
                    f"AOI full_union policy produced non-polygonal geometry: {geom.geom_type!r}"
                )
            out = gpd.GeoDataFrame({"geometry": [geom]}, geometry="geometry", crs=gdf.crs)

        elif mode == "by_fields":
            if not request.dissolve_fields:
                raise AOIValidationError("dissolve_mode='by_fields' requires dissolve_fields")

            missing = [f for f in request.dissolve_fields if f not in gdf.columns]
            if missing:
                raise AOIValidationError(f"Missing dissolve fields: {missing}")

            out = gdf.dissolve(by=list(request.dissolve_fields), as_index=False)

        elif mode == "preserve_features":
            out = gdf.copy()

        else:
            raise AOIValidationError(f"Unsupported dissolve_mode: {mode!r}")

        report["overlaps_present_after_policy"] = self._has_overlaps(out)
        report["overlaps_resolved_by_policy"] = (
            report["overlaps_detected_before_policy"]
            and not report["overlaps_present_after_policy"]
        )

        if not request.allow_overlaps and report["overlaps_present_after_policy"]:
            raise AOIValidationError(
                "AOI policy output contains overlapping polygons, but allow_overlaps=False."
            )

        return out, report


    def _extract_polygonal(
        self,
        geom,
    ) -> tuple[Polygon | MultiPolygon | None, dict[str, int]]:
        meta = {
            "input_component_count": 0,
            "polygon_component_count": 0,
            "nonpolygon_component_drop_count": 0,
        }

        if geom is None or geom.is_empty:
            return None, meta

        if isinstance(geom, Polygon):
            meta["input_component_count"] = 1
            meta["polygon_component_count"] = 1
            return geom, meta

        if isinstance(geom, MultiPolygon):
            count = len(geom.geoms)
            meta["input_component_count"] = count
            meta["polygon_component_count"] = count
            return geom, meta

        if isinstance(geom, GeometryCollection):
            polys = []
            meta["input_component_count"] = len(geom.geoms)

            for part in geom.geoms:
                if isinstance(part, Polygon):
                    polys.append(part)
                    meta["polygon_component_count"] += 1
                elif isinstance(part, MultiPolygon):
                    polys.extend(list(part.geoms))
                    meta["polygon_component_count"] += len(part.geoms)
                else:
                    meta["nonpolygon_component_drop_count"] += 1

            if not polys:
                return None, meta

            merged = unary_union(polys)

            if isinstance(merged, Polygon):
                return merged, meta
            if isinstance(merged, MultiPolygon):
                return merged, meta

            return None, meta

        # Any non-polygonal standalone geometry
        meta["input_component_count"] = 1
        meta["nonpolygon_component_drop_count"] = 1
        return None, meta

    def _has_overlaps(self, gdf: gpd.GeoDataFrame) -> bool:
        if gdf.empty or len(gdf) < 2:
            return False

        geoms = list(gdf.geometry)
        for i in range(len(geoms)):
            gi = geoms[i]
            if gi is None or gi.is_empty:
                continue

            for j in range(i + 1, len(geoms)):
                gj = geoms[j]
                if gj is None or gj.is_empty:
                    continue

                if not gi.intersects(gj):
                    continue

                inter = gi.intersection(gj)
                if not inter.is_empty and inter.area > 0:
                    return True

        return False