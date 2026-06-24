from ast_engine.config.registry import enrichment, utils, models
from ast_engine.config.registry.models import BaseDataset
from ast_engine.core.data_adapters.base import DatasetInfo

from pathlib import Path
from unittest.mock import MagicMock
import pytest

# Real test data - Test_Shape_A is a single polygon in EPSG:3005 with a "Name"
# column (same fixtures the adapter tests use).
DATA_DIR = Path(__file__).parents[1] / "data" / "Test_Shape_A"
SHP = DATA_DIR / "Test_Shape_A_shp" / "Test_Shape_A.shp"

# A finished registry saved as YAML - the shape a registry takes on disk and
# what the orchestrator loads at run time. Path is anchored to this file so the
# test passes no matter which folder pytest runs from.
SAMPLE_REGISTRY = Path(__file__).parents[1] / "data" / "sample_registry.yaml"

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


@pytest.mark.unit
def test_util_hydrate_datasets():
    '''Test hydrate datasets from dict
    '''
    # load sample registry
    basedatasets = utils.hydrate_base_datasets(DATA_DICT)
    assert len(basedatasets) == 2
    assert basedatasets[0].name == "Mapsheet"
    assert basedatasets[1].datasource == "WHSE_ADMIN_BOUNDARIES.ADM_NR_DISTRICTS_SP"


# ---------------------------------------------------------------------------
# Load a saved registry from YAML - the archetype for working with the data
# registry. A finished registry lives on disk as YAML; the orchestrator loads
# it with load_yaml() and reads each dataset's fields to drive the pipeline.
# This is the worked example of that read path - no database, no mocks, just
# the sample registry data in the repo.
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_load_registry_from_yaml():
    '''Load the sample registry and read the fields a consumer relies on.'''
    registry = utils.load_yaml(SAMPLE_REGISTRY)

    # Registry-level: a version string and a list of datasets.
    assert registry.version == "1.0"
    assert len(registry.datasets) == 2

    # Every entry comes back as a fully-typed RegistryDataset.
    assert all(isinstance(d, models.RegistryDataset) for d in registry.datasets)

    # Read the first dataset the way the orchestrator does.
    mapsheet = registry.datasets[0]
    assert mapsheet.name == "Mapsheet"
    assert mapsheet.datasource == "WHSE_BASEMAPPING.BCGS_20K_GRID"
    assert mapsheet.data_adapter == "ORACLE"          # which adapter to use
    assert mapsheet.crs == "EPSG:3005"
    assert mapsheet.geometry_type == "POLYGON"
    assert "OBJECTID" in mapsheet.columns
    assert mapsheet.aggregate_columns == ["MAP_TILE_DISPLAY_NAME"]

    # definition_query is parsed into the structured `where` on load, so a
    # consumer can compile it for either database without re-parsing the string.
    assert mapsheet.definition_query == "FCODE = 'RG90020000'"
    assert mapsheet.where is not None

@pytest.mark.unit
def test_hydrate_base_datasets():
    ''' Test dataset hydration'''
    indata = [DATA_DICT[0]]
    dsets = utils.hydrate_base_datasets(indata)
    assert len(dsets) == 1
    assert dsets[0].name == DATA_DICT[0]["name"]
    assert dsets[0].datasource == DATA_DICT[0]["datasource"]

@pytest.mark.unit
def test_registry_creation(monkeypatch):
    ''' Test registry creation'''
    # DATA_DICT is all BCGW (Oracle) tables; patch describe() and pass a mock
    # connection so the build runs offline (no live database).
    info = DatasetInfo(
        geom_column="SHAPE",
        crs="EPSG:3005",
        geometry_type="polygon",
        columns=["OBJECTID"],
        row_count=10,
    )
    monkeypatch.setattr(
        enrichment.OracleAdapter, "describe", lambda self, *, table: info
    )

    dsets = utils.hydrate_base_datasets(DATA_DICT)
    registry_datasets = []
    for d in dsets:
        enrich_data = enrichment.Enrich(d, connection=MagicMock(), cursor=MagicMock())
        enrich_data.enrich()
        rd = enrich_data.build()
        registry_datasets.append(rd)
    output = models.Registry(version="0.1", datasets=registry_datasets)
    assert output.version == "0.1"
    assert len(output.datasets) == 2

@pytest.mark.unit
def test_ingest_spreadsheet():
    ''' Test spreadsheet ingestion'''
    template_dict = {
        "name": "Featureclass_Name(valid characters only)",
        "datasource": "Datasource",
        "aggregate_columns": [
            "Fields_to_Summarize",
            "Fields_to_Summarize2",
            "Fields_to_Summarize3",
            "Fields_to_Summarize4",
            "Fields_to_Summarize5",
            "Fields_to_Summarize6",
        ],
        "definition":"Definition_Query",
    }

    data = utils.ingest_spreadsheet(template=template_dict, inp_xlsx=str(DATA_DIR.parent / "Test_Registry.xlsx"))
    assert len(data)>0
@pytest.mark.unit
def test_ingest_spreadsheet_to_model():
    ''' Test spreadsheet ingestion'''
    template_dict = {
        "name": "Featureclass_Name(valid characters only)",
        "datasource": "Datasource",
        "aggregate_columns": [
            "Fields_to_Summarize",
            "Fields_to_Summarize2",
            "Fields_to_Summarize3",
            "Fields_to_Summarize4",
            "Fields_to_Summarize5",
            "Fields_to_Summarize6",
        ],
        "definition":"Definition_Query",
    }

    data = utils.ingest_spreadsheet(template=template_dict, inp_xlsx=str(DATA_DIR.parent / "Test_Registry.xlsx"))
    dsets = utils.hydrate_base_datasets(data)
    assert len(dsets) > 0


# ---------------------------------------------------------------------------
# resolve_adapter - route a datasource to the right adapter by its shape.
# A path (slash) or a known geo file type is a FILE; SCHEMA.TABLE is ORACLE.
# This is the routing that used to miss BCGW tables under non-WHSE schemas.
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.parametrize(
    "datasource, expected",
    [
        ("WHSE_BASEMAPPING.BCGS_20K_GRID", "ORACLE"),
        ("WHSE_ADMIN_BOUNDARIES.ADM_NR_DISTRICTS_SP", "ORACLE"),
        ("REG_LAND_AND_NATURAL_RESOURCE.SOME_TABLE", "ORACLE"),   # non-WHSE schema
        ("REG_IMAGERY_AND_BASE_MAPS.SOME_LAYER", "ORACLE"),       # non-WHSE schema
        (r"W:\data\base.gdb\some_layer", "FILE"),                 # gdb + layer
        ("/data/parcels.shp", "FILE"),                            # flat file with path
        ("W:/data/cache.gpkg/some_layer", "FILE"),                # gpkg + layer
        ("Test_Shape_A.kmz", "FILE"),                             # flat file, no path
    ],
)
def test_resolve_adapter_routes(datasource, expected):
    base = BaseDataset(name="x", datasource=datasource)
    assert enrichment.Enrich(base).resolve_adapter() == expected


@pytest.mark.unit
def test_resolve_adapter_raises_on_unresolvable():
    base = BaseDataset(name="x", datasource="just_a_word")
    with pytest.raises(ValueError):
        enrichment.Enrich(base).resolve_adapter()


# ---------------------------------------------------------------------------
# enrich() - the file path reads real metadata; the Oracle path is mocked so
# no database is touched. Both map the adapter's DatasetInfo onto the registry
# fields and build a RegistryDataset.
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_enrich_from_file_real_data():
    """Enrich a real shapefile end-to-end (no mocks) and build the dataset."""
    base = BaseDataset(name="Test Shape A", datasource=str(SHP))
    e = enrichment.Enrich(base)
    e.enrich()

    assert e.data_adapter == "FILE"
    assert e.geometry_type == "polygon"
    assert e.crs == "EPSG:3005"
    assert "Name" in e.columns
    assert e.row_count == 1

    dataset = e.build()
    assert isinstance(dataset, models.RegistryDataset)
    assert dataset.geom_column == e.geom_column
    assert dataset.row_count == 1


@pytest.mark.unit
def test_enrich_from_oracle_maps_describe(monkeypatch):
    """The Oracle path maps describe()'s DatasetInfo onto the registry fields.
    describe() is patched, so no Oracle connection is used."""
    info = DatasetInfo(
        geom_column="SHAPE",
        crs="EPSG:3005",
        geometry_type="line",
        columns=["OBJECTID", "ROAD_NAME"],
        row_count=99,
    )
    monkeypatch.setattr(
        enrichment.OracleAdapter, "describe", lambda self, *, table: info
    )

    base = BaseDataset(name="Roads", datasource="WHSE_TRANSPORT.TRANSPORT_LINE")
    e = enrichment.Enrich(base, connection=MagicMock(), cursor=MagicMock())
    e.enrich()

    assert e.data_adapter == "ORACLE"
    assert e.geometry_type == "line"
    assert e.geom_column == "SHAPE"
    assert e.row_count == 99

    dataset = e.build()
    assert dataset.crs == "EPSG:3005"
    assert dataset.columns == ["OBJECTID", "ROAD_NAME"]


@pytest.mark.unit
def test_enrich_oracle_without_connection_raises():
    """An Oracle dataset with no connection gives a clear error, not bad data."""
    base = BaseDataset(name="Roads", datasource="WHSE_TRANSPORT.TRANSPORT_LINE")
    with pytest.raises(ValueError):
        enrichment.Enrich(base).enrich()
