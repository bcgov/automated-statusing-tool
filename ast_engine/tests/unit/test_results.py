""" 
Results model tests 

Purpose:
- 
- This test ensures that the results model is working as intended, with correct 
    metric calculations and JSON serialization.
- Ensure each result type reports the right headline number and unit 
    - i.e. point overlay -> _count_; polygon -> polygon → _total area_ (m²)
    line → _total length_ (m); proximity → _nearest distance_ (m); 
    adjacency → _total shared boundary_ (m);
- An empty proximity result should report 0; `spatial_link` will be empty (orchestrator fills it);
- A result bundle can be saved to JSON and read back with each result keeping its type.


HOW TO EXTEND:
-------------
1. A

Example:
def test_point_overlay_count()
def test_polygon_overlay_area()
def test_line_overlay_length()
def test_proximity_nearest_distance()
def test_empty_proximity_returns_zero()
def test_adjacency_shared_boundary()
def test_spatial_link_empty_by_default()
def test_bundle_roundtrip_json()

"""

import pytest
from datetime import datetime, UTC
from ast_engine.core.results import (
    AstResults, PointOverlayResult, PolyOverlayResult, LineOverlayResult,
    ProximityResult, AdjacencyResult, FeatureRecord, DatasetResultGroup
)

# Tags every test in this file as "unit"
# replaces a per-function @pytest.mark.unit decorator on each test
pytestmark = pytest.mark.unit

def test_point_overlay_count():
    result = PointOverlayResult(
        features=[FeatureRecord(feature_id="p1"), FeatureRecord(feature_id="p2")]
    )
    assert result.measure_value == 2.0
    assert result.measure_unit == "count"

def test_polygon_overlay_area():
    result = PolyOverlayResult(total_area=1500.5)
    assert result.measure_value == 1500.5
    assert result.measure_unit == "square meters"


def test_line_overlay_length():
    result = LineOverlayResult(total_length=2000.0)
    assert result.measure_value == 2000.0
    assert result.measure_unit == "meters"


def test_proximity_nearest_distance():
    result = ProximityResult(
        features=[
            FeatureRecord(feature_id="f1", measure=100.0),
            FeatureRecord(feature_id="f2", measure=50.0),
        ]
    )
    assert result.measure_value == 50.0  # minimum
    assert result.measure_unit == "meters"


def test_empty_proximity_returns_zero():
    result = ProximityResult(features=[])
    assert result.measure_value == 0.0

def test_adjacency_shared_boundary():
    result = AdjacencyResult(
        is_adjacent=True,
        features=[
            FeatureRecord(feature_id="a1", measure=100.0),
            FeatureRecord(feature_id="a2", measure=50.0),
        ]
    )
    assert result.measure_value == 150.0  # sum
    assert result.measure_unit == "meters"

def test_spatial_link_empty_by_default():
    result = PointOverlayResult()
    assert result.spatial_link is None

def test_bundle_roundtrip_json():
    bundle = AstResults(
        job_id="test_job",
        aoi_id="test_aoi",
        results=[
            DatasetResultGroup(
                dataset_id="ds1",
                dataset_name="Test Dataset",
                results=[PointOverlayResult(features=[FeatureRecord(feature_id="p1")])]
            )
        ]
    )
    # Serialize
    json_str = bundle.model_dump_json()
    # Deserialize
    restored = AstResults.model_validate_json(json_str)
    
    assert restored.job_id == "test_job"
    assert len(restored.results) > 0