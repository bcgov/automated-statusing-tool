
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, List, Literal

import geopandas as gpd

from .models import AOIRequest, AreaOfInterest
from .exceptions import AOIValidationError
from .normalizer import AOINormalizer
from .inspector import AOIInspector
from .validator import AOIValidator
from .parts_builder import AOIPartBuilder


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

    def from_gdf(
        self,
        request: AOIRequest,
        raw_gdf: gpd.GeoDataFrame,
        *,
        raise_errors: bool = True,
    ) -> AreaOfInterest:
        normalized = self.normalizer.normalize_aoi(raw_gdf, request)

        parts = self.part_builder.build_parts(
            request.aoi_id,
            normalized.gdf,
        )

        properties = self.inspector.inspect(normalized.gdf, parts)
        validation = self.validator.validate(
            gdf=normalized.gdf,
            report=normalized.report,
            parts=parts,
            properties=properties,
        )

        if raise_errors and not validation.is_valid:
            messages = "\n".join(f"{i.code}: {i.message}" for i in validation.issues)
            raise AOIValidationError(messages)

        return AreaOfInterest(
            aoi_id=request.aoi_id,
            name=request.name,
            gdf=normalized.gdf,
            normalization_report=normalized.report,
            properties=properties,
            parts=parts,
            validation=validation,
        )
