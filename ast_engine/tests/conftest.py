from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def tests_root() -> Path:
    return Path(__file__).resolve().parent


@pytest.fixture
def test_data_dir(tests_root: Path) -> Path:
    return tests_root / "data"