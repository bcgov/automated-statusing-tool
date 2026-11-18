from pathlib import Path

# <project>/ast_engine/config/paths.py → <project>
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def project_path(value: str | Path, *, root: Path = PROJECT_ROOT) -> Path:
    root = Path(root).expanduser()
    if not root.is_absolute():
        raise ValueError("config_root must be an absolute path.")
    return (root / Path(value).expanduser()).resolve(strict=False)