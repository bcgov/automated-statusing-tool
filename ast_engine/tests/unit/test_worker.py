"""Tests for the job worker: the AOI options a job carries (#219), and how a job
ends - COMPLETED, or FAILED with the reason in job.error. No BCGW connection is needed.
"""

import json
from types import SimpleNamespace
from uuid import uuid4

import geopandas as gpd
import pytest
from pydantic import SecretStr, ValidationError
from shapely.geometry import box

from ast_engine.config.registry.models import DataAdapter
from ast_engine.workers import worker
from ast_engine.workers.worker import AstJob, JobStatus, run_worker
from shared_models.models import AOIOptions

pytestmark = pytest.mark.unit

# AOI rows are drawn in BC Albers (EPSG:3005) and sent as GeoJSON (EPSG:4326), as the
# API does. Each cell is 100 m x 100 m (1 ha); cells sit 50 m apart, so none touch.
X0, Y0 = 1_200_000.0, 500_000.0


def _cell(column, size=100.0):
    x = X0 + column * 150.0
    return box(x, Y0, x + size, Y0 + size)


# Block A is two separate cells, block B is one.
THREE_ROWS = [({"BLOCK": "A"}, _cell(0)), ({"BLOCK": "A"}, _cell(1)), ({"BLOCK": "B"}, _cell(2))]


def _job(rows=THREE_ROWS, **aoi_options):
    """A job with no datasets: enough to test the AOI and how the job ends."""
    gdf = gpd.GeoDataFrame(
        [attributes for attributes, _ in rows],
        geometry=[geometry for _, geometry in rows],
        crs="EPSG:3005",
    )
    return AstJob(
        job_id=uuid4(),
        registries=[],
        user="tester",
        aoi_id="test_aoi",
        aoi_name="Test AOI",
        aoi=json.loads(gdf.to_crs("EPSG:4326").to_json()),
        aoi_options=AOIOptions(**aoi_options),
        status=JobStatus.QUEUED,
    )


@pytest.fixture
def connections(monkeypatch):
    """Record each BCGW connection the worker opens, instead of opening one."""
    opened = []

    class FakeConnection:
        def __init__(self, **kwargs):
            self.closed = False
            opened.append(self)

        def close(self):
            self.closed = True

    monkeypatch.setattr(worker, "OracleConnection", FakeConnection)
    return opened


@pytest.fixture
def analysed_aoi(monkeypatch):
    """Keep the AOI the worker hands to the engine, instead of running the analysis."""
    seen = {}

    def fake_run_analysis(**kwargs):
        seen["aoi"] = kwargs["aoi"]

    monkeypatch.setattr(worker, "run_analysis", fake_run_analysis)
    return seen


# --- The options ----------------------------------------------------------------

def test_aoi_options_default_to_one_area():
    options = AOIOptions()

    assert options.dissolve_mode == "full_union"
    assert options.dissolve_fields == []
    assert options.allow_overlaps is False
    assert options.part_policy == "multi_part"


def test_a_job_without_aoi_options_gets_the_defaults():
    job = AstJob(job_id=uuid4(), registries=[], user="u", aoi_id="a", aoi_name="A", aoi={},
                 status=JobStatus.QUEUED)

    assert job.aoi_options == AOIOptions()
    assert job.error is None


@pytest.mark.parametrize(
    "options, reason",
    [
        ({"dissolve_mode": "by_fields"}, "needs at least one dissolve field"),
        ({"dissolve_fields": ["BLOCK"]}, "only be used with dissolve_mode 'by_fields'"),
        ({"dissolve_mode": "by_fields", "dissolve_fields": ["BLOCK", " BLOCK "]}, "same field twice"),
        ({"dissolve_mode": "dissolve_everything"}, "dissolve_mode"),
        ({"part_policy": "exploded"}, "not available yet"),
        ({"group_by": "BLOCK"}, "group_by"),
    ],
)
def test_aoi_options_refuse_what_the_aoi_builder_would_refuse(options, reason):
    with pytest.raises(ValidationError, match=reason):
        AOIOptions(**options)


def test_blank_dissolve_field_names_are_dropped():
    options = AOIOptions(dissolve_mode="by_fields", dissolve_fields=[" BLOCK ", ""])

    assert options.dissolve_fields == ["BLOCK"]


@pytest.mark.parametrize(
    "aoi_options, expected_parts",
    [
        ({}, 1),
        ({"dissolve_mode": "by_fields", "dissolve_fields": ["BLOCK"]}, 2),
        ({"dissolve_mode": "preserve_features"}, 3),
    ],
)
def test_the_aoi_options_decide_the_aoi_parts(analysed_aoi, aoi_options, expected_parts):
    job = run_worker(_job(**aoi_options))

    assert job.status == JobStatus.COMPLETED
    assert len(analysed_aoi["aoi"].gdf) == expected_parts


# --- How a job ends -------------------------------------------------------------

def test_a_job_with_no_bcgw_datasets_completes_without_a_connection(connections):
    job = run_worker(_job(dissolve_mode="by_fields", dissolve_fields=["BLOCK"]))

    assert job.status == JobStatus.COMPLETED
    assert job.error is None
    assert connections == []


def test_a_missing_dissolve_field_fails_the_job_with_the_reason():
    job = run_worker(_job(dissolve_mode="by_fields", dissolve_fields=["ZONE"]))

    assert job.status == JobStatus.FAILED
    assert "missing dissolve field" in job.error
    assert "ZONE" in job.error


def test_overlapping_parts_fail_the_job_unless_overlaps_are_allowed():
    # Two 1 ha cells overlapping by 50 m.
    overlapping = [({"BLOCK": "A"}, _cell(0)), ({"BLOCK": "B"}, box(X0 + 50, Y0, X0 + 150, Y0 + 100))]

    failed = run_worker(_job(overlapping, dissolve_mode="preserve_features"))
    allowed = run_worker(_job(overlapping, dissolve_mode="preserve_features", allow_overlaps=True))

    assert failed.status == JobStatus.FAILED
    assert "overlapping" in failed.error
    assert allowed.status == JobStatus.COMPLETED


def test_a_sliver_piece_fails_the_job_with_the_reason():
    # A 20 m x 20 m piece is 0.04 ha, under the 0.1 ha sliver limit.
    with_sliver = [({"BLOCK": "A"}, _cell(0)), ({"BLOCK": "B"}, _cell(1, size=20.0))]

    job = run_worker(_job(with_sliver))

    assert job.status == JobStatus.FAILED
    assert "sliver" in job.error


def test_a_rejected_aoi_never_opens_bcgw(monkeypatch, connections):
    monkeypatch.setattr(worker, "build_tasks", lambda registries: [SimpleNamespace(source_type=DataAdapter.ORACLE)])

    job = run_worker(_job(dissolve_mode="by_fields", dissolve_fields=["ZONE"]))

    assert job.status == JobStatus.FAILED
    assert connections == []


def test_bcgw_is_opened_for_a_bcgw_dataset_and_closed_even_when_the_run_fails(monkeypatch, connections):
    monkeypatch.setattr(worker.settings, "oracle_password", SecretStr("not-a-real-password"))
    monkeypatch.setattr(worker, "build_tasks", lambda registries: [SimpleNamespace(source_type=DataAdapter.ORACLE)])

    def run_analysis_that_fails(**kwargs):
        assert kwargs["oracle_connection"] is connections[0]
        raise RuntimeError("lost the BCGW connection")

    monkeypatch.setattr(worker, "run_analysis", run_analysis_that_fails)

    job = run_worker(_job())

    assert len(connections) == 1
    assert connections[0].closed
    assert job.status == JobStatus.FAILED
    # The details stay in the log; the job gets a plain message.
    assert "lost the BCGW connection" not in job.error
