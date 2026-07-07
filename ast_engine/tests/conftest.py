from __future__ import annotations

import pytest

from ast_engine.core.aoi import AOIBuilder, AOIBuildRequest


@pytest.fixture
def aoi_builder() -> AOIBuilder:
    return AOIBuilder()


@pytest.fixture
def make_aoi_build_request():
    def _make_aoi_build_request(*, spec, raw_gdf) -> AOIBuildRequest:
        return AOIBuildRequest(
            spec=spec,
            raw_gdf=raw_gdf,
        )

    return _make_aoi_build_request