import yaml
from .models import Registry, BaseDataset
from pathlib import Path

def load_yaml(file_path: Path) -> Registry:
    with open("registry.yaml", "r") as f:
        data = yaml.safe_load(f)
    registry = Registry(**data)
    return registry

def dump_yaml(registry: Registry, file_path: Path):
    with open(file_path, "w") as f:
        yaml.dump(registry.model_dump(), f, sort_keys=False)

def hydrate_base_datasets(seed: list[dict]) -> list[BaseDataset]:
    '''Hydrates a list of BaseDatasets from a dictionary
    -------------
    example:
    -------------
    seed = [
    {
        "name": "Mapsheet",
        "datasource": "WHSE_BASEMAPPING.BCGS_20K_GRID",
        "definition_query": "FCODE = 'RG90020000'",
        "aggregate_columns": ["MAP_TILE_DISPLAY_NAME"],
    },
    ]
    '''
    return [BaseDataset(**item) for item in seed]
