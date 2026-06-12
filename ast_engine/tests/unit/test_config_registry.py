from ast_engine.config.registry import enrichment, utils, models
from pathlib import Path


DATA_DICT = [
        {
            "name": "Mapsheet",
            "datasource": "WHSE_BASEMAPPING.BCGS_20K_GRID",
            "definition_query": "FCODE = 'RG90020000'",
            "aggregate_columns": ["MAP_TILE_DISPLAY_NAME"],
        },
        {
            "name": "Natural Resource Districts",
            "datasource": "WHSE_ADMIN_BOUNDARIES.ADM_NR_DISTRICTS_SP",
            "aggregate_columns": ["DISTRICT_NAME"],
        },
    ]


def test_util_hydrate_datasets():
    '''Test hydrate datasets from dict
    '''
    # load sample registry
    basedatasets = utils.hydrate_base_datasets(DATA_DICT)
    assert len(basedatasets) == 2
    assert basedatasets[0].name == "Mapsheet"
    assert basedatasets[1].datasource == "WHSE_ADMIN_BOUNDARIES.ADM_NR_DISTRICTS_SP"


def test_util_load_yaml():
    ''' Test create Registry from yaml
    '''    
    registry = utils.load_yaml(Path('./tests/data/sample_registry.yaml'))
    assert registry.version=="1.0"
    assert len(registry.datasets)==2
    assert registry.datasets[0].crs=="EPSG:3005"
   
def test_hydrate_base_datasets():
    ''' Test dataset hydration'''
    indata = [DATA_DICT[0]]
    dsets = utils.hydrate_base_datasets(indata)
    assert len(dsets) == 1
    assert dsets[0].name == DATA_DICT[0]["name"]
    assert dsets[0].datasource == DATA_DICT[0]["datasource"]

def test_registry_creation():
    ''' Test registry creation'''
    dsets = utils.hydrate_base_datasets(DATA_DICT)
    registry_datasets = []
    for d in dsets:
        enrich_data = enrichment.Enrich(d)
        enrich_data.enrich()
        rd = enrich_data.build()
        registry_datasets.append(rd)
    output = models.Registry(version="0.1", datasets=registry_datasets)
    assert output.version == "0.1"
    assert len(output.datasets) == 2