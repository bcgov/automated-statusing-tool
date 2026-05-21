# tests/conftest.py
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
AST_ROOT = REPO_ROOT / "ast"

sys.path.insert(0, str(AST_ROOT))
