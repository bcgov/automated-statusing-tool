
"""
Import tests for AST modules.

Purpose:
- Ensure each AST module can be imported successfully
- Catch missing dependencies or bad import logic early
- Provide a simple, explicit list of modules for new developers

HOW TO EXTEND:
-------------
1. Add new module names to AST_MODULES
2. Keep names short and readable
3. Do not include submodules unless they contain logic (eg. init, constants)

Example:
    "aoi"
    "data_adapters"
    "ast_core.status"
"""

import importlib
import pytest

pytestmark = pytest.mark.unit

AST_MODULES = [
    "core.aoi",
    "core.data_adapters",
    "core.data_adapters.kml",
    "core.data_adapters.oracle",
    "core.operator",
    "core.operator.adjacent",
    "core.operator.overlay",
    "core.operator.proximity"
]

@pytest.mark.parametrize("module_name", AST_MODULES)
def test_module_imports_cleanly(module_name):
    """
    Each module should import without:
    - raising exceptions
    - requiring external services
    - executing heavy logic at import time
    """

    importlib.import_module(module_name)


