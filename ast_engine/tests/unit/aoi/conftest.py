from __future__ import annotations

from unittest.mock import create_autospec
import pytest

from ast_engine.core.aoi import AOIBuilder
from ast_engine.core.aoi.models import AOIValidationResult
from ast_engine.core.aoi.validator import AOIValidator

@pytest.fixture
def aoi_builder() -> AOIBuilder:
    return AOIBuilder(
        validator=AOIValidator(
            spatial_validator=None,
        )
    )

@pytest.fixture
def aoi_validator_stub():
    stub = create_autospec(AOIValidator, instance=True)
    stub.validate.return_value = AOIValidationResult()
    return stub


@pytest.fixture
def aoi_builder_with_validation(aoi_validator_stub) -> AOIBuilder:
    return AOIBuilder(validator=aoi_validator_stub)
