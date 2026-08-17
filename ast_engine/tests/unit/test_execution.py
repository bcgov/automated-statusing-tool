"""
Orchestrator (execution) tests.

These run the orchestrator the way a real run does - AOI, a list of analysis
tasks, one assembled AstResults - but with local files instead of a database, so
no BCGW connection is needed.

What we check:
- an end-to-end run over the three operators (overlay / within_distance /
  adjacency) returns the right AstResults shape and result types;
- one dataset's failure is isolated: its group comes back empty and marked
  status="failure", and the rest of the run still produces results. A dataset
  that ran but found nothing stays "success", so the two are told apart;
- the per-task helpers route correctly (table for Oracle, path for files; the
  attribute filter is forwarded to the adapter);
- the registry -> task mapper fills the task fields (and lower-cases the geometry
  type), skips a dataset with no operator, and tags provenance across registries;
- saving the spatial output: off by default, one GeoPackage per dataset when it
  is on, nothing written for a dataset with no matches, and a failed write never
  costs the analysis result.

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
    _safe_filename,
    _source_kwargs,
    build_tasks,
    run_analysis,
    tasks_from_registry,
)
from ast_engine.config.settings import Settings
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


def _registry(datasets):
    """Wrap datasets in a Registry for the mapper tests.

    os / date / id are provenance the registry records when it is built. The
    orchestrator never reads them, so fixed values are fine - they are here
    only because the registry model requires them.
    """
    return Registry(
        version="1.0",
        os="nt",
        date="2026-07-30 00:00:00",
        id="test-registry",
        datasets=datasets,
    )


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
    assert bad.status == "failure"                 # ...and marked, so it is not read as "nothing found"
    assert bad.error                               # with the reason kept for the analyst
    assert len(good.results) == 1                  # the good dataset still ran
    assert good.status == "success"
    assert good.error is None
    assert good.results[0].feature_count == 2


def test_a_dataset_with_no_matches_is_a_success_not_a_failure():
    """The empty-vs-failed check: nothing found still counts as a dataset that ran."""
    far_point = DATA_DIR / "Test_Proximity" / "proximity_2_km.shp"
    task = _file_task("1", "far", far_point, "within_distance", distance_m=100)

    result = run_analysis(aoi=_valid_aoi(), tasks=[task], job_id="job-7")

    group = result.results[0]
    assert group.status == "success"               # the read worked
    assert group.error is None
    assert group.results[0].feature_count == 0     # there was just nothing near the AOI


# --- Saving the spatial output ----------------------------------------------
# record_spatial is off by default; when it is on, each dataset's matched
# features are saved as a GeoPackage under temp_dir and the file path is recorded
# on the result as spatial_link.

def _overlay_task() -> AnalysisTask:
    """One polygon overlay task - 2 of the 3 test polygons match the AOI."""
    return _file_task("1", "test polys", POLYGONS, "overlay", geom_type="polygon")


def test_record_spatial_off_writes_nothing(tmp_path):
    """The default: no files, and spatial_link stays empty."""
    settings = Settings(record_spatial=False, temp_dir=str(tmp_path))

    result = run_analysis(aoi=_valid_aoi(), tasks=[_overlay_task()], job_id="job-3", settings=settings)

    assert result.results[0].results[0].spatial_link is None
    assert list(tmp_path.iterdir()) == []


def test_record_spatial_writes_a_gpkg_and_records_the_path(tmp_path):
    """One GeoPackage per dataset, in a folder named after the analysis."""
    settings = Settings(record_spatial=True, temp_dir=str(tmp_path))

    result = run_analysis(aoi=_valid_aoi(), tasks=[_overlay_task()], job_id="job-4", settings=settings)

    # the space in "test polys" is replaced so the name works as a file name
    written = tmp_path / "overlay" / "test_polys.gpkg"
    assert written.exists()

    saved = result.results[0].results[0]
    assert saved.spatial_link == str(written)

    # the features are saved as they were read - same count as the result
    on_disk = gpd.read_file(written)
    assert len(on_disk) == saved.feature_count
    # the operator's working column is renamed on the way out, so what an analyst
    # opens says what the number is and what unit it is in
    assert "overlap_area_m2" in on_disk.columns
    assert "_overlay_measure" not in on_disk.columns


def test_record_spatial_skips_a_dataset_with_no_matches(tmp_path):
    """Nothing found means nothing to save - no empty file, no link."""
    far_point = DATA_DIR / "Test_Proximity" / "proximity_2_km.shp"
    task = _file_task("1", "far", far_point, "within_distance", distance_m=100)
    settings = Settings(record_spatial=True, temp_dir=str(tmp_path))

    result = run_analysis(aoi=_valid_aoi(), tasks=[task], job_id="job-5", settings=settings)

    assert result.results[0].results[0].feature_count == 0
    assert result.results[0].results[0].spatial_link is None
    assert list(tmp_path.iterdir()) == []


def test_a_failed_write_keeps_the_analysis_result(tmp_path, monkeypatch):
    """A file that cannot be written is logged and skipped - the result survives."""
    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(gpd.GeoDataFrame, "to_file", boom)
    settings = Settings(record_spatial=True, temp_dir=str(tmp_path))

    result = run_analysis(aoi=_valid_aoi(), tasks=[_overlay_task()], job_id="job-6", settings=settings)

    saved = result.results[0].results[0]
    assert saved.feature_count == 2        # the analysis still came through
    assert saved.spatial_link is None      # but nothing was saved


def test_safe_filename_cleans_registry_names():
    """Registry names carry spaces and brackets; the file name keeps only safe characters."""
    assert _safe_filename("Indian Reserves (Tab 1)") == "Indian_Reserves_Tab_1"
    assert _safe_filename("///") == "dataset"


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
    registry = _registry(
        [
            _registry_dataset(
                "Districts", "WHSE_ADMIN.ADM_NR_DISTRICTS_SP", "ORACLE",
                {"type": "overlay"}, geometry_type="POLYGON", unique_id="OBJECTID",
            ),
            _registry_dataset(
                "Roads", "C:/data/roads.shp", "FILE",
                {"type": "within_distance", "distance_m": 50.0}, geometry_type="line",
            ),
        ]
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
    registry = _registry(
        [
            _registry_dataset("HasOp", "WHSE.A", "ORACLE", {"type": "overlay"}),
            _registry_dataset("NoOp", "WHSE.B", "ORACLE", None),
        ]
    )
    tasks = tasks_from_registry(registry)
    assert [t.dataset_name for t in tasks] == ["HasOp"]   # the operator-less row is skipped


def test_build_tasks_concatenates_with_provenance():
    reg_a = _registry([_registry_dataset("A", "WHSE.A", "ORACLE", {"type": "overlay"})])
    reg_b = _registry([_registry_dataset("B", "WHSE.B", "ORACLE", {"type": "overlay"})])

    tasks = build_tasks([("provincial", reg_a), ("west_coast", reg_b)])
    assert [t.dataset_name for t in tasks] == ["A", "B"]
    assert [t.source_registry for t in tasks] == ["provincial", "west_coast"]
