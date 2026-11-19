from __future__ import annotations

import pytest

from ast_engine.core.aoi.aoi_builder import AOIBuilder
from ast_engine.core.aoi.validator import AOIValidator


@pytest.fixture
def aoi_builder() -> AOIBuilder:
    return AOIBuilder(
        validator=AOIValidator(
            spatial_validator=None,
        )
    )