"""
Orchestrator (execution) tests.

These run the orchestrator the way a real run does - AOI, a list of analysis
tasks, one assembled AstResults - but with local files instead of a database, so
no BCGW connection is needed.

What we check:
- an end-to-end run over the three operators (overlay / within_distance /
  adjacency) returns the right AstResults shape and result types;
- one dataset's failure is isolated: its group comes back empty and the rest of
  the run still produces results;
- the per-task helpers route correctly (table for Oracle, path for files; the
  attribute filter is forwarded to the adapter);
- the registry -> task mapper fills the task fields (and lower-cases the geometry
  type), skips a dataset with no operator, and tags provenance across registries.

The AOI is the Test_Shape_A box (a rectangle in BC Albers / EPSG:3005).
"""

import pytest
from pathlib import Path

import geopandas as gpd

from ast_engine.core.aoi.aoi_builder import AOIBuilder, AOIRequest, AreaOfInterest
from ast_engine.core.data_adapters.base import BaseSpatialAdapter, DatasetInfo
from ast_engine.core.execution import (
    AnalysisTask,
    _pick_adapter,
    _run_operator,
    _source_kwargs,
    run_analysis,
    tasks_from_registries,
    tasks_from_registry,
)
from ast_engine.core.results import (
    AdjacencyResult,
    AstResults,
    PolyOverlayResult,
    ProximityResult,
)
from ast_engine.config.registry.models import Registry, RegistryDataset
from ast_engine.core.data_adapters.file.adapter import FileSpatialAdapter

pytestmark = pytest.mark.unit


# --- Test data --------------------------------------------------------------
DATA_DIR = Path(__file__).parents[1] / "data"
SHP = DATA_DIR / "Test_Shape_A" / "Test_Shape_A_shp" / "Test_Shape_A.shp"  # the AOI box
POINTS = DATA_DIR / "Test_Overlay" / "points.shp"
POLYGONS = DATA_DIR / "Test_Overlay" / "polygons.shp"


# --- Helpers ----------------------------------------------------------------
def _valid_aoi() -> AreaOfInterest:
    """A normal AOI in BC Albers (metres) - what the operators expect."""
    gdf = gpd.read_file(SHP)
    return AOIBuilder().from_gdf(AOIRequest(aoi_id="test_aoi", name="Test AOI"), gdf)


def _file_task(dataset_id, name, datasource, operator, **kwargs) -> AnalysisTask:
    """A file-source AnalysisTask with the given operator + params."""
    return AnalysisTask(
        dataset_id=dataset_id,
        dataset_name=name,
        source_type="file",
        datasource=str(datasource),
        operator=operator,
        **kwargs,
    )


class RecordingAdapter(BaseSpatialAdapter):
    """A stand-in data source that records what it was asked for and returns nothing.

    Lets us confirm the orchestrator hands the adapter the right dataset identity
    (table vs path) and the attribute filter, without touching a file or a DB.
    """

    def __init__(self):
        self.last_options = None
        self.last_source_kwargs = None

    def read(self, *, read_options=None, target_crs=None, **source_kwargs):
        self.last_options = read_options
        self.last_source_kwargs = source_kwargs
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:3005")

    def _read_impl(self, *, read_options, **source_kwargs):
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:3005")

    def describe(self, **source_kwargs) -> DatasetInfo:
        raise NotImplementedError


def _registry_dataset(name, datasource, data_adapter, operator, geometry_type="POLYGON", **extra):
    """Build a minimal-but-valid RegistryDataset for the mapper tests."""
    fields = dict(
        id=name,
        name=name,
        datasource=datasource,
        columns=["OBJECTID"],
        geom_column="GEOMETRY",
        geometry_type=geometry_type,
        crs="EPSG:3005",
        data_adapter=data_adapter,
        row_count=1,
        operator=operator,
        aggregate_columns=["NAME"],
    )
    fields.update(extra)
    return RegistryDataset(**fields)


# --- End-to-end (file-based, no DB) -----------------------------------------
def test_end_to_end_file_run_assembles_results():
    """Three file datasets, one per operator -> one AstResults with three groups."""
    aoi = _valid_aoi()
    tasks = [
        _file_task("1", "polys", POLYGONS, "overlay", geom_type="polygon", keep_properties=["Name"]),
        _file_task("2", "points", POINTS, "within_distance", distance_m=100_000),
        _file_task("3", "box", SHP, "adjacency", tolerance_m=0),
    ]

    result = run_analysis(aoi=aoi, tasks=tasks, job_id="job-1")

    assert isinstance(result, AstResults)
    assert result.job_id == "job-1"
    assert result.aoi_id == aoi.aoi_id
    assert len(result.results) == 3

    groups = {group.dataset_name: group for group in result.results}
    # each group holds exactly one typed result, of the operator's type
    assert isinstance(groups["polys"].results[0], PolyOverlayResult)
    assert groups["polys"].results[0].feature_count == 2          # outside polygon dropped
    assert isinstance(groups["points"].results[0], ProximityResult)
    assert groups["points"].results[0].feature_count >= 1
    # the box dataset is the AOI itself, so it shares its whole boundary
    assert isinstance(groups["box"].results[0], AdjacencyResult)
    assert groups["box"].results[0].is_adjacent is True


def test_per_task_error_isolation():
    """A bad-path dataset comes back as an empty group; the run still produces results."""
    aoi = _valid_aoi()
    tasks = [
        _file_task("bad", "missing", DATA_DIR / "does_not_exist.shp", "overlay", geom_type="polygon"),
        _file_task("good", "polys", POLYGONS, "overlay", geom_type="polygon"),
    ]

    result = run_analysis(aoi=aoi, tasks=tasks, job_id="job-2")

    assert len(result.results) == 2
    bad = next(g for g in result.results if g.dataset_name == "missing")
    good = next(g for g in result.results if g.dataset_name == "polys")
    assert bad.results == []                       # failure recorded as an empty group
    assert len(good.results) == 1                  # the good dataset still ran
    assert good.results[0].feature_count == 2


# --- Routing helpers --------------------------------------------------------
def test_source_kwargs_oracle_vs_file():
    oracle = AnalysisTask("1", "t", "oracle", "WHSE.ABC", "overlay")
    file = AnalysisTask("2", "t", "file", "C:/data/x.shp", "overlay")
    assert _source_kwargs(oracle) == {"table": "WHSE.ABC"}
    assert _source_kwargs(file) == {"path": "C:/data/x.shp"}


def test_pick_adapter_routes_by_source_type():
    file_adapter = FileSpatialAdapter()
    oracle_adapter = RecordingAdapter()  # stand-in object
    file_task = AnalysisTask("1", "t", "file", "x.shp", "overlay")
    oracle_task = AnalysisTask("2", "t", "oracle", "WHSE.ABC", "overlay")

    assert _pick_adapter(file_task, file_adapter, oracle_adapter) is file_adapter
    assert _pick_adapter(oracle_task, file_adapter, oracle_adapter) is oracle_adapter


def test_pick_adapter_oracle_without_connection_raises():
    file_task = FileSpatialAdapter()
    oracle_task = AnalysisTask("2", "t", "oracle", "WHSE.ABC", "overlay")
    with pytest.raises(RuntimeError):
        _pick_adapter(oracle_task, file_task, None)


def test_run_operator_passes_table_and_where_for_oracle():
    """An Oracle task hands the adapter table=... and the attribute filter."""
    adapter = RecordingAdapter()
    task = AnalysisTask(
        "1", "t", "oracle", "WHSE.ABC", "overlay",
        geom_type="polygon", where={"conditions": [{"field": "FCODE", "op": "=", "value": "RG90"}]},
    )
    _run_operator(task, _valid_aoi(), adapter)
    assert adapter.last_source_kwargs == {"table": "WHSE.ABC"}
    assert adapter.last_options.where == task.where


# --- Registry -> task mapper ------------------------------------------------
def test_tasks_from_registry_maps_fields_and_lowercases_geom():
    registry = Registry(
        version="1.0",
        datasets=[
            _registry_dataset(
                "Districts", "WHSE_ADMIN.ADM_NR_DISTRICTS_SP", "ORACLE",
                {"type": "overlay"}, geometry_type="POLYGON", unique_id="OBJECTID",
            ),
            _registry_dataset(
                "Roads", "C:/data/roads.shp", "FILE",
                {"type": "within_distance", "distance_m": 50.0}, geometry_type="line",
            ),
        ],
    )

    tasks = tasks_from_registry(registry, source_registry="provincial")
    assert len(tasks) == 2

    districts, roads = tasks
    assert districts.operator == "overlay"
    assert districts.source_type == "oracle"             # data_adapter lower-cased
    assert districts.geom_type == "polygon"              # geometry_type lower-cased
    assert districts.feature_id_field == "OBJECTID"
    assert districts.keep_properties == ["NAME"]
    assert districts.source_registry == "provincial"

    assert roads.operator == "within_distance"
    assert roads.distance_m == 50.0
    assert roads.source_type == "file"
    assert roads.datasource == "C:/data/roads.shp"


def test_tasks_from_registry_skips_dataset_without_operator():
    registry = Registry(
        version="1.0",
        datasets=[
            _registry_dataset("HasOp", "WHSE.A", "ORACLE", {"type": "overlay"}),
            _registry_dataset("NoOp", "WHSE.B", "ORACLE", None),
        ],
    )
    tasks = tasks_from_registry(registry)
    assert [t.dataset_name for t in tasks] == ["HasOp"]   # the operator-less row is skipped


def test_tasks_from_registries_concatenates_with_provenance():
    reg_a = Registry(version="1.0", datasets=[_registry_dataset("A", "WHSE.A", "ORACLE", {"type": "overlay"})])
    reg_b = Registry(version="1.0", datasets=[_registry_dataset("B", "WHSE.B", "ORACLE", {"type": "overlay"})])

    tasks = tasks_from_registries([("provincial", reg_a), ("west_coast", reg_b)])
    assert [t.dataset_name for t in tasks] == ["A", "B"]
    assert [t.source_registry for t in tasks] == ["provincial", "west_coast"]
