from copy import deepcopy
from .models import Registry, BaseDataset
import pandas as pd
from pathlib import Path
import yaml

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


def ingest_spreadsheet(template: dict, inp_xlsx: str): # Or should the input be xlsx
    '''
    Ingest spreadsheet and create a dictionary to hydrate the base dataset
    This assumes a flat dictionary and does not recurse
    '''
    inp_df = pd.read_excel(inp_xlsx)
    dataset_list = []
    for index, row in inp_df.iterrows():
        row_dataset = deepcopy(template)
        if pd.notna(row["Featureclass_Name(valid characters only)"]):
            # do the lookup
            for key, value in template.items():
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, str):
                            row_dataset[key][value.index(item)] = row[item]
                        elif pd.isna(row[item]):
                                del(row_dataset[key][value.index(item)]) # This may cause skipping
                                # Drop value
                                pass
                elif isinstance(value, str):
                    row_dataset[key] = row[value]
                elif pd.isna(row[value]):
                    del(row_dataset[key]) # This may cause skipping
                    # drop value
                    pass
                else:
                    print(f"error {value} is not a string or a list")
            # Append dataset to list
            dataset_list.append(row_dataset)
    return dataset_list
