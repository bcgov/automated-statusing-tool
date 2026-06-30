from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, TypeVar

from .models import (
    AreaOfInterest,
    AOIBuildRequest,
    AOIBuildResult,
)

from .exceptions import (
    root_cause,
    AOIBuildError,
    AOIError,
)

from .normalizer import AOINormalizer
from .inspector import AOIInspector
from .validator import AOIValidator
from .parts_builder import AOIPartBuilder

logger = logging.getLogger(__name__)

T = TypeVar("T")


class AOIBuilder:
    """
    Builds a clean, normalized, inspected, and validated AreaOfInterest
    from a raw GeoDataFrame.
    """

    def __init__(
        self,
        normalizer: AOINormalizer | None = None,
        inspector: AOIInspector | None = None,
        validator: AOIValidator | None = None,
        part_builder: AOIPartBuilder | None = None,
    ) -> None:
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

        normalized = self._run_stage(
            stage="normalization",
            build_aoi_id=spec.aoi_id,
            operation=self.normalizer.normalize_aoi,
            gdf=request.raw_gdf,
            request=spec,
        )

        parts = self._run_stage(
            stage="part_building",
            build_aoi_id=spec.aoi_id,
            operation=self.part_builder.build_parts,
            aoi_id=spec.aoi_id,
            gdf=normalized.gdf,
        )

        properties = self._run_stage(
            stage="inspection",
            build_aoi_id=spec.aoi_id,
            operation=self.inspector.inspect,
            gdf=normalized.gdf,
            parts=parts,
        )

        validation = self._run_stage(
            stage="validation",
            build_aoi_id=spec.aoi_id,
            operation=self.validator.validate,
            gdf=normalized.gdf,
            report=normalized.report,
            parts=parts,
            properties=properties,
        )

        aoi = self._run_stage(
            stage="aoi_construction",
            build_aoi_id=spec.aoi_id,
            operation=AreaOfInterest,
            aoi_id=spec.aoi_id,
            name=spec.name,
            gdf=normalized.gdf,
            properties=properties,
            parts=parts,
        )

        result = AOIBuildResult(
            aoi=aoi,
            validation=validation,
            normalization_report=normalized.report,
        )

        self._log_build_summary(result)

        return result

    def _run_stage(
        self,
        *,
        stage: str,
        build_aoi_id: str,
        operation: Callable[..., T],
        **operation_kwargs: Any,
    ) -> T:
        try:
            return operation(**operation_kwargs)

        except AOIBuildError:
            raise

        except AOIError as exc:
            root = root_cause(exc)

            logger.error(
                "AOI build stage failed | aoi_id=%s | stage=%s | "
                "error_type=%s | root_error_type=%s | reason=%s | root_reason=%s",
                build_aoi_id,
                stage,
                type(exc).__name__,
                type(root).__name__,
                exc,
                root,
            )

            logger.debug(
                "AOI build stage root traceback | aoi_id=%s | stage=%s",
                build_aoi_id,
                stage,
                exc_info=(type(root), root, root.__traceback__),
            )

            raise AOIBuildError(
                f"Could not build AOI {build_aoi_id!r}; "
                f"failed during {stage}: {root}",
                stage=stage,
                aoi_id=build_aoi_id,
            ) from exc

        except Exception as exc:
            logger.exception(
                "Unexpected AOI build stage failure | "
                "aoi_id=%s | stage=%s | error_type=%s",
                build_aoi_id,
                stage,
                type(exc).__name__,
            )

            raise AOIBuildError(
                f"Unexpected error building AOI {build_aoi_id!r}; "
                f"failed during {stage}.",
                stage=stage,
                aoi_id=build_aoi_id,
            ) from exc

    def _log_build_summary(
        self,
        result: AOIBuildResult,
    ) -> None:
        aoi = result.aoi
        validation = result.validation

        logger.info(
            "AOI build complete | aoi_id=%s | area_ha=%.4f | part_count=%s",
            aoi.aoi_id,
            aoi.footprint_area_ha,
            aoi.part_count,
        )

        if validation.has_errors:
            logger.warning(
                "AOI validation completed with errors | "
                "aoi_id=%s | errors=%s | warnings=%s | infos=%s",
                aoi.aoi_id,
                len(validation.errors),
                len(validation.warnings),
                len(validation.infos),
            )

        elif validation.has_warnings:
            logger.info(
                "AOI validation completed with warnings | "
                "aoi_id=%s | warnings=%s | infos=%s",
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