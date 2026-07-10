from __future__ import annotations

import pytest

from ast_engine.core.aoi.aoi_builder import AOIBuilder
from ast_engine.core.aoi.models import AOIBuildRequest
from ast_engine.core.aoi.validator import AOIValidator


@pytest.fixture
def aoi_builder() -> AOIBuilder:
    # Include call with spatial validator to complete the call.
    # Will need to build spatial validator for this to work,
    # but for now we can just pass None.
    aoi_validator = AOIValidator(
        spatial_validator=None,
    )
    return AOIBuilder(validator=aoi_validator)


@pytest.fixture
def make_aoi_build_request():
    def _make_aoi_build_request(*, spec, raw_gdf) -> AOIBuildRequest:
        return AOIBuildRequest(
            spec=spec,
            raw_gdf=raw_gdf,
        )

    return _make_aoi_build_request