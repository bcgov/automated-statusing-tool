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
- saving the spatial output: off by default, one GeoPackage per AOI part (named
  <dataset>_<part id>) when it is on, nothing written for a dataset with no
  matches, and a failed write never costs the analysis result;
- the run's diagnostic events are written to a JSONL file when asked;
- results per AOI part: each dataset returns one result per AOI row, labelled
  with the row's attributes; a multipart row is still one part.

The AOI is the Test_Shape_A box (a rectangle in BC Albers / EPSG:3005). It is
one row, so each dataset returns one part.
"""

import json
import pytest
from pathlib import Path

import geopandas as gpd
import pyogrio
from shapely.geometry import MultiPolygon, box
from uuid import UUID

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
from ast_engine.utils.diagnostics import DiagnosticTracker

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


def _west_and_east_halves(gap_m=0.0):
    """The Test_Shape_A box cut into a west and an east half, gap_m apart."""
    minx, miny, maxx, maxy = _valid_aoi().gdf.total_bounds
    mid = (minx + maxx) / 2
    west = box(minx, miny, mid - gap_m / 2, maxy)
    east = box(mid + gap_m / 2, miny, maxx, maxy)
    return west, east


def _two_row_aoi() -> AreaOfInterest:
    """An AOI of two rows (west and east halves) kept as they are, each with a label."""
    west, east = _west_and_east_halves()
    gdf = gpd.GeoDataFrame({"label": ["west", "east"]}, geometry=[west, east], crs="EPSG:3005")
    request = AOIRequest(aoi_id="test_aoi", name="Two rows", dissolve_mode="preserve_features")
    return AOIBuilder().from_gdf(request, gdf)


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
    job_id = UUID("12345678-1234-5678-1234-567812345678")
    result = run_analysis(aoi=aoi, tasks=tasks, job_id=job_id)

    assert isinstance(result, AstResults)
    assert result.job_id == job_id
    assert result.aoi_id == aoi.aoi_id
    assert len(result.results) == 3

    groups = {group.dataset_name: group for group in result.results}
    # a one-row AOI: each group holds exactly one part, with a typed result of the operator's type
    assert all(len(group.parts) == 1 for group in result.results)
    assert isinstance(groups["polys"].parts[0].result, PolyOverlayResult)
    assert groups["polys"].parts[0].result.feature_count == 2          # outside polygon dropped
    assert isinstance(groups["points"].parts[0].result, ProximityResult)
    assert groups["points"].parts[0].result.feature_count >= 1
    # the box dataset is the AOI itself, so it shares its whole boundary
    assert isinstance(groups["box"].parts[0].result, AdjacencyResult)
    assert groups["box"].parts[0].result.is_adjacent is True


def test_per_task_error_isolation():
    """A bad-path dataset comes back as an empty group; the run still produces results."""
    aoi = _valid_aoi()
    tasks = [
        _file_task("bad", "missing", DATA_DIR / "does_not_exist.shp", "overlay", geom_type="polygon"),
        _file_task("good", "polys", POLYGONS, "overlay", geom_type="polygon"),
    ]
    job_id = UUID("22345678-1234-5678-1234-567812345678")
    result = run_analysis(aoi=aoi, tasks=tasks, job_id=job_id)

    assert len(result.results) == 2
    bad = next(g for g in result.results if g.dataset_name == "missing")
    good = next(g for g in result.results if g.dataset_name == "polys")
    assert bad.parts == []                         # failure recorded as an empty group
    assert bad.status == "failure"                 # ...and marked, so it is not read as "nothing found"
    assert bad.error                               # with the reason kept for the analyst
    assert len(good.parts) == 1                    # the good dataset still ran
    assert good.status == "success"
    assert good.error is None
    assert good.parts[0].result.feature_count == 2


def test_a_dataset_with_no_matches_is_a_success_not_a_failure():
    """The empty-vs-failed check: nothing found still counts as a dataset that ran."""
    far_point = DATA_DIR / "Test_Proximity" / "proximity_2_km.shp"
    task = _file_task("1", "far", far_point, "within_distance", distance_m=100)
    job_id = UUID("72345678-1234-5678-1234-567812345678")
    result = run_analysis(aoi=_valid_aoi(), tasks=[task], job_id=job_id)

    group = result.results[0]
    assert group.status == "success"               # the read worked
    assert group.error is None
    assert group.parts[0].result.feature_count == 0   # there was just nothing near the AOI


# --- Saving the spatial output ----------------------------------------------
# record_spatial is off by default; when it is on, each AOI part's matched
# features are saved as a GeoPackage under temp_dir, named after the dataset and
# the part, and the file path is recorded on that part's result as spatial_link.

def _overlay_task() -> AnalysisTask:
    """One polygon overlay task - 2 of the 3 test polygons match the AOI."""
    return _file_task("1", "test polys", POLYGONS, "overlay", geom_type="polygon")


def test_record_spatial_off_writes_nothing(tmp_path):
    """The default: no files, and spatial_link stays empty."""
    settings = Settings(record_spatial=False, temp_dir=str(tmp_path))
    job_id = UUID("32345678-1234-5678-1234-567812345678")
    result = run_analysis(aoi=_valid_aoi(), tasks=[_overlay_task()], job_id=job_id, settings=settings)

    assert result.results[0].parts[0].result.spatial_link is None
    assert list(tmp_path.iterdir()) == []


def test_record_spatial_writes_a_gpkg_and_records_the_path(tmp_path):
    """One GeoPackage per AOI part, named <dataset>_<part id>, under the analysis."""
    settings = Settings(record_spatial=True, temp_dir=str(tmp_path))
    job_id = UUID("42345678-1234-5678-1234-567812345678")
    result = run_analysis(aoi=_valid_aoi(), tasks=[_overlay_task()], job_id=job_id, settings=settings)

    # the space in "test polys" is replaced so the name works as a file name;
    # the AOI is one row, so there is one part file
    written = tmp_path / "overlay" / "test_polys_test_aoi_part_1.gpkg"
    assert written.exists()
    # the layer inside takes the file's name, so a GIS shows the dataset and the part
    assert pyogrio.list_layers(written)[0][0] == "test_polys_test_aoi_part_1"

    saved = result.results[0].parts[0].result
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
    job_id = UUID("52345678-1234-5678-1234-567812345678")
    result = run_analysis(aoi=_valid_aoi(), tasks=[task], job_id=job_id, settings=settings)

    assert result.results[0].parts[0].result.feature_count == 0
    assert result.results[0].parts[0].result.spatial_link is None
    assert list(tmp_path.iterdir()) == []


def test_a_failed_write_keeps_the_analysis_result(tmp_path, monkeypatch):
    """A file that cannot be written is logged and skipped - the result survives."""
    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(gpd.GeoDataFrame, "to_file", boom)
    settings = Settings(record_spatial=True, temp_dir=str(tmp_path))
    job_id = UUID("62345678-1234-5678-1234-567812345678")
    result = run_analysis(aoi=_valid_aoi(), tasks=[_overlay_task()], job_id=job_id, settings=settings)

    saved = result.results[0].parts[0].result
    assert saved.feature_count == 2        # the analysis still came through
    assert saved.spatial_link is None      # but nothing was saved


def test_same_dataset_name_in_two_registries_writes_two_files(tmp_path):
    """Two registries can carry the same dataset name - each keeps its own file.

    Tab 1 is a selection of datasets that also sit in the provincial registry, so
    a run covering both sees the same name twice. The registry folder is what
    keeps the two outputs apart; without it the second write replaced the first.
    """
    tasks = [
        _file_task("1", "Provincial Forest", POLYGONS, "overlay",
                   geom_type="polygon", source_registry="tab1"),
        _file_task("2", "Provincial Forest", POLYGONS, "overlay",
                   geom_type="polygon", source_registry="provincial"),
    ]
    settings = Settings(record_spatial=True, temp_dir=str(tmp_path))
    job_id = UUID("72345678-1234-5678-1234-567812345678")
    result = run_analysis(aoi=_valid_aoi(), tasks=tasks, job_id=job_id, settings=settings)

    from_tab1 = tmp_path / "tab1" / "overlay" / "Provincial_Forest_test_aoi_part_1.gpkg"
    from_provincial = tmp_path / "provincial" / "overlay" / "Provincial_Forest_test_aoi_part_1.gpkg"
    assert from_tab1.exists()
    assert from_provincial.exists()

    # each result points at its own file, not at a shared one
    links = [group.parts[0].result.spatial_link for group in result.results]
    assert links == [str(from_tab1), str(from_provincial)]
    # and each result records the registry it came from
    assert [group.parts[0].result.registry for group in result.results] == ["tab1", "provincial"]


def test_safe_filename_cleans_registry_names():
    """Registry names carry spaces and brackets; the file name keeps only safe characters."""
    assert _safe_filename("Indian Reserves (Tab 1)") == "Indian_Reserves_Tab_1"
    assert _safe_filename("///") == "dataset"


# --- Results per AOI part ---------------------------------------------------
# A part is one row of the AOI, as its dissolve rule left it. Each dataset is
# read once, then measured against each part on its own. Both test polygons that
# overlap the Test_Shape_A box sit in its west half.

def test_two_row_aoi_gives_one_labelled_result_per_row():
    """Two rows -> two results per dataset, each labelled from its row. The halves
    don't overlap, so the per-part areas add up to the one-row answer."""
    job_id = UUID("82345678-1234-5678-1234-567812345678")
    whole = run_analysis(aoi=_valid_aoi(), tasks=[_overlay_task()], job_id=job_id).results[0].parts[0]
    parts = run_analysis(aoi=_two_row_aoi(), tasks=[_overlay_task()], job_id=job_id).results[0].parts

    assert [p.aoi_part_id for p in parts] == ["test_aoi_part_1", "test_aoi_part_2"]
    assert [p.part_attributes for p in parts] == [{"label": "west"}, {"label": "east"}]
    assert [p.result.feature_count for p in parts] == [2, 0]
    assert sum(p.part_area_ha for p in parts) == pytest.approx(whole.part_area_ha)
    assert sum(p.result.total_area for p in parts) == pytest.approx(whole.result.total_area)


def test_a_multipart_row_is_one_part():
    """One row made of two separate pieces is still one part, measured as one area."""
    west, east = _west_and_east_halves(gap_m=100)
    gdf = gpd.GeoDataFrame(geometry=[MultiPolygon([west, east])], crs="EPSG:3005")
    aoi = AOIBuilder().from_gdf(AOIRequest(aoi_id="test_aoi", name="Two pieces"), gdf)
    job_id = UUID("92345678-1234-5678-1234-567812345678")
    parts = run_analysis(aoi=aoi, tasks=[_overlay_task()], job_id=job_id).results[0].parts

    assert len(parts) == 1
    assert parts[0].part_area_ha == pytest.approx((west.area + east.area) / 10_000)
    assert parts[0].part_attributes == {}          # full_union keeps no attributes


def test_rows_with_the_same_field_value_are_reported_together():
    """Grouped by a field (by_fields), two separate "A" rows are ONE part, and the
    "First" polygon, which falls in both of them, is listed once for A with its
    whole overlap."""
    polygons = gpd.read_file(POLYGONS).to_crs("EPSG:3005")
    first = polygons.loc[polygons["Name"] == "First"].geometry.iloc[0]
    minx, miny, maxx, maxy = _valid_aoi().gdf.total_bounds
    mid = (minx + maxx) / 2
    cut = first.centroid.x                          # the two A rows are 2 m apart, right through "First"
    a1, a2 = box(minx, miny, cut - 1, maxy), box(cut + 1, miny, mid, maxy)
    rows = gpd.GeoDataFrame({"group": ["A", "A", "B"]}, geometry=[a1, a2, box(mid, miny, maxx, maxy)], crs="EPSG:3005")
    request = AOIRequest(aoi_id="test_aoi", name="Groups", dissolve_mode="by_fields", dissolve_fields=("group",))
    task = _file_task("1", "test polys", POLYGONS, "overlay", geom_type="polygon", keep_properties=["Name"])
    job_id = UUID("c2345678-1234-5678-1234-567812345678")

    parts = run_analysis(aoi=AOIBuilder().from_gdf(request, rows), tasks=[task], job_id=job_id).results[0].parts

    assert [p.part_attributes for p in parts] == [{"group": "A"}, {"group": "B"}]
    first_in_a = [f for f in parts[0].result.features if f.properties["Name"] == "First"]
    assert len(first_in_a) == 1                     # listed once, not once per row
    assert first_in_a[0].measure == pytest.approx(first.intersection(a1.union(a2)).area)


def test_record_spatial_writes_one_file_per_part(tmp_path):
    """Each part with matches gets its own GeoPackage, named after the dataset and the part."""
    settings = Settings(record_spatial=True, temp_dir=str(tmp_path))
    job_id = UUID("a2345678-1234-5678-1234-567812345678")
    result = run_analysis(aoi=_two_row_aoi(), tasks=[_overlay_task()], job_id=job_id, settings=settings)
    west, east = result.results[0].parts

    written = tmp_path / "overlay" / "test_polys_test_aoi_part_1.gpkg"
    assert west.result.spatial_link == str(written)
    assert len(gpd.read_file(written)) == west.result.feature_count
    # nothing matched in the east half, so nothing is saved for it
    assert east.result.spatial_link is None
    assert [p.name for p in written.parent.iterdir()] == ["test_polys_test_aoi_part_1.gpkg"]


def test_run_events_are_written_to_jsonl(tmp_path):
    """Asked for a JSONL file, the tracker writes every event of the run to it -
    including run_start, whose job_id is a UUID that plain JSON cannot hold."""
    path = tmp_path / "run.jsonl"
    job_id = UUID("b2345678-1234-5678-1234-567812345678")
    run_analysis(aoi=_valid_aoi(), tasks=[_overlay_task()], job_id=job_id,
                 tracker=DiagnosticTracker(jsonl_path=path))

    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [event["step"] for event in events] == ["run_start", "dataset_done", "run_complete"]
    assert events[0]["extra"]["job_id"] == str(job_id)


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
    assert adapter.last_source_kwargs["table"] == "WHSE.ABC"
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
