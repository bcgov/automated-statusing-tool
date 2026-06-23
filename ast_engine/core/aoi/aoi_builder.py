
from __future__ import annotations

import logging

from .models import (
    AreaOfInterest,
    AOIBuildRequest,
    AOIBuildResult
)

from .exceptions import (
    root_cause,
    AOIBuildError,
    AOIError
)

from .normalizer import AOINormalizer
from .inspector import AOIInspector
from .validator import AOIValidator
from .parts_builder import AOIPartBuilder

logger = logging.getLogger(__name__)


class AOIBuilder:
    """
    Builds a clean, normalized, and validated AreaOfInterest from a raw GeoDataFrame.

    All validated geometries are intended to be part of one output statusing report package.
    This module does not own policy for splitting by region or other criteria. Input data should be
    pre-buffered for non-polygon geometry requests. The AOI normalization will resolve conflicts (overlaps)
    as per the AOI policy, which effectively creates the units for the overlay engine.
    """
    def __init__(
        self,
        normalizer: AOINormalizer | None = None,
        inspector: AOIInspector | None = None,
        validator: AOIValidator | None = None,
        part_builder: AOIPartBuilder | None = None,
    ):
        self.normalizer = normalizer or AOINormalizer()
        self.inspector = inspector or AOIInspector()
        self.validator = validator or AOIValidator()
        self.part_builder = part_builder or AOIPartBuilder()


    def build_from_request(
        self,
        request: AOIBuildRequest,
    ) -> AOIBuildResult:
        spec = request.spec

        logger.info(
            "Starting AOI build | aoi_id=%s | name=%s",
            spec.aoi_id,
            spec.name,
        )

        try:
            normalized = self.normalizer.normalize_aoi(
                gdf=request.raw_gdf,
                request=spec,
            )

            parts = self.part_builder.build_parts(
                aoi_id=spec.aoi_id,
                gdf=normalized.gdf,
            )

            properties = self.inspector.inspect(
                gdf=normalized.gdf,
                parts=parts,
            )

            validation = self.validator.validate(
                # aoi_id=spec.aoi_id,
                gdf=normalized.gdf,
                report=normalized.report,
                parts=parts,
                properties=properties,
                # context=request.validation_context,
            )

            aoi = AreaOfInterest(
                aoi_id=spec.aoi_id,
                name=spec.name,
                gdf=normalized.gdf,
                properties=properties,
                parts=parts,
            )

        except AOIBuildError:
            raise

        except AOIError as exc:
            root = root_cause(exc)

            logger.error(
                "AOI normalization failed | aoi_id=%s | name=%s | error_type=%s | reason=%s",
                spec.aoi_id,
                spec.name,
                type(root).__name__,
                root,
            )

            logger.debug(
                "AOI normalization root traceback",
                exc_info=(type(root), root, root.__traceback__),
            )

            raise AOIBuildError(
                f"Could not build AOI {spec.aoi_id!r}: {root}"
            ) from exc
        
        except Exception as exc:
            logger.exception(
                "Unexpected AOI build failure | aoi_id=%s | name=%s | error_type=%s",
                spec.aoi_id,
                spec.name,
                type(exc).__name__,
            )
            raise AOIBuildError(
                f"Unexpected error building AOI {spec.aoi_id!r}."
            ) from exc

        result = AOIBuildResult(
            aoi=aoi,
            validated=validation,
            normalized=normalized.report,
        )

        self._log_build_summary(result)

        return result
    

    def _log_build_summary(
        self,
        result: AOIBuildResult,
    ) -> None:
        aoi = result.aoi
        validation = result.validated

        logger.info(
            "AOI build complete | aoi_id=%s | area_ha=%.4f | part_count=%s",
            aoi.aoi_id,
            aoi.footprint_area_ha,
            aoi.part_count,
        )

        if validation.has_errors:
            logger.warning(
                "AOI validation completed with errors | aoi_id=%s | errors=%s | warnings=%s | infos=%s",
                aoi.aoi_id,
                len(validation.errors),
                len(validation.warnings),
                len(validation.infos),
            )

        elif validation.has_warnings:
            logger.info(
                "AOI validation completed with warnings | aoi_id=%s | warnings=%s | infos=%s",
                aoi.aoi_id,
                len(validation.warnings),
                len(validation.infos),
            )

        else:
            logger.info(
                "AOI validation passed | aoi_id=%s | infos=%s",
                aoi.aoi_id,
                len(validation.infos),
            )