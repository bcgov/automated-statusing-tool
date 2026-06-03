import yaml
from models import Registry
from pathlib import Path

def load_yaml(file_path: Path) -> Registry:
    with open("registry.yaml", "r") as f:
        data = yaml.safe_load(f)
    registry = Registry(**data)
    return registry

def dump_yaml(registry: Registry, file_path: Path):
    with open(file_path, "w") as f:
        yaml.dump(registry.model_dump(), f, sort_keys=False)

