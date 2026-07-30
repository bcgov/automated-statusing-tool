from copy import deepcopy
from .models import Registry, BaseDataset
import pandas as pd
from pathlib import Path
import yaml

import logging
logger = logging.getLogger(__name__)

def load_yaml(file_path: Path) -> Registry:
    from os import name
    logger.debug(f"Loading YAML file {file_path}")
    with open(file_path, "r") as f:
        data = yaml.safe_load(f)
    registry = Registry(**data)
    if not registry.os == name:
        raise ValueError(f"Registry OS type {registry.os} does not match current OS {name}")
    return registry

def dump_yaml(registry: Registry, file_path: Path):
    logger.debug(f"Dumping YAML file {file_path}")
    with open(file_path, "w") as f:
        # by_alias=True so a where LogicalGroup is written with its 'and' / 'or'
        # keys (not the Python field names 'and_' / 'or_'); otherwise load_yaml
        # cannot parse the where back. Matches enrichment.build()'s dump.
        yaml.dump(registry.model_dump(by_alias=True), f, sort_keys=False)

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


def infer_operator(buffer_distance) -> dict:
    '''Tab 2 rule: turn the spreadsheet Buffer_Distance into an operator block.
    A blank or zero distance is an overlap (intersect); a positive distance is
    a within_distance buffer of that many metres. This is what keeps the buffer
    distance out of the dataset name string.

    Tab 2 only ever yields overlay or within_distance - the spreadsheet carries
    no k or tolerance. If Tab 2 datasets ever need nearest or adjacency, this is
    the function to revise (the operator model already supports all four types).'''
    if buffer_distance is None or pd.isna(buffer_distance) or float(buffer_distance) <= 0:
        return {"type": "overlay"}
    return {"type": "within_distance", "distance_m": float(buffer_distance)}


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
            # Tab 2: derive the operator from the Buffer_Distance column
            # (blank/0 -> overlap, >0 -> within_distance).
            row_dataset["operator"] = infer_operator(row.get("Buffer_Distance"))
            # Append dataset to list
            dataset_list.append(row_dataset)
    return dataset_list

def path_translate(in_path:str, path_dict:dict|None = None) -> str:
    '''
    Translates paths from nt (windows) to posix (linux) or vice versa
        in_path: the path to translate
        path_dict: string replaces to do
                    Usually to translate a windows share to a mount location on linux
                    ex: "\\\\network.share\\projects":"/mnt/projects"
    '''
    from os import name
    from os.path import dirname, exists
    if name == "nt":

        in_path = in_path.replace("/", "\\")
    elif name == "posix":

        if path_dict is not None:
            for old, new in path_dict.items():
                in_path = in_path.replace(old, new)
        else:
            logger.warning("Warning: No path translation provided. Absolute paths may be invalid")
        in_path = in_path.replace("\\", "/")
    return in_path

def drive_map_loader(drive_map_path:str, delimiter:str= "|") -> dict:
    '''
    Loads and interpretes the drive mapping dictionary
        map_path: path to the .conf file
        delimiter: optional delimiter. Assumed delimiter is a pipe (|)

    Output: dictionary of share:mount_location


    '''
    conf_dict = {}
    with open(drive_map_path, "r") as f:
        for line in f:
            if line and not line.startswith("#"):
                key, value = line.split(delimiter, 1)
                conf_dict[key.strip()] = value.strip()

    return conf_dict

class RegistryBuilder():
    '''
    Accepts a list of registry datasets and builds up the metadata required
    Parameters:
    version (optional)
    os_type (optional)
    date (optional)
    id (internal)
    datasets (required)

    '''
    def __init__(self, datasets, version:str = "0.1", os_type:str|None = None, date = None ):
        self.version = version
        self.os_type = os_type
        self.date = date
        self.datasets = datasets
    def enrich(self):
        '''
        Generate the values where applicable
        '''
        import uuid
        if self.os_type not in ["posix", "nt"]:
            from os import name
            self.os_type = name
        if self.date is None:
            from datetime import datetime
            self.date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.id = str(uuid.uuid4())
    def build(self) -> Registry:
        '''
        Build the registry object
        '''
        self.enrich()
        registry = Registry(
            version=self.version, 
            os=self.os_type, 
            date=self.date, 
            id=self.id, 
            datasets=self.datasets)
        return registry



