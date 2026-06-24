# tests/conftest.py
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
#AST_ROOT = REPO_ROOT / "ast_engine"

sys.path.insert(0, str(REPO_ROOT))
