from copy import deepcopy
from .models import Registry, BaseDataset
import pandas as pd
from pathlib import Path
import yaml

import logging
logger = logging.getLogger(__name__)

def load_yaml(file_path: Path) -> Registry:
    logger.debug(f"Loading YAML file {file_path}")
    with open(file_path, "r") as f:
        data = yaml.safe_load(f)
    registry = Registry(**data)
    return registry

def dump_yaml(registry: Registry, file_path: Path):
    logger.debug(f"Dumping YAML file {file_path}")
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
    logger.debug(f"Hydrating datasets: Count {len(seed)}")
    return [BaseDataset(**item) for item in seed]


def ingest_spreadsheet(template: dict, inp_xlsx: str) -> list: # Or should the input be xlsx
    '''
    Ingest spreadsheet and create a dictionary to hydrate the base dataset
    This assumes a flat dictionary and does not recurse
    '''
    inp_df = pd.read_excel(inp_xlsx)
    dataset_list = []
    for index, row in inp_df.iterrows():
        row_dataset = {}
        if pd.notna(row["Featureclass_Name(valid characters only)"]):
            # do the lookup
            for key, value in template.items():
                if isinstance(value, list):
                    if key not in row_dataset.keys():
                        row_dataset[key] = []
                    for item in value:
                        if isinstance(item, str):
                            if pd.notna(row[item]):
                                    row_dataset[key].append(row[item])
                elif isinstance(value, str):
                    if pd.notna(row[value]):
                        row_dataset[key] = row[value]
                else:
                    logger.error(f"error {value} is not a string or a list")
            # Append dataset to list
            dataset_list.append(row_dataset)
    return dataset_list
