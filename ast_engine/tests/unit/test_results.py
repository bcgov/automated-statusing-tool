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
1. Create a new test function per result type to validate. 
2. Ensure to test any special circumstance (i.e. empty proximity results).
3. Keep test names short and readable
4. Should have no need to use test data (can create dummy result objects)

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


# ---------------------------------------------------------------------------
# Added during review - feature_count, an empty adjacency, and a round-trip
# that checks every result type comes back as the right type.
# ---------------------------------------------------------------------------

def test_feature_count_is_number_of_features():
    """feature_count is the number of features, separate from the headline measure."""
    result = ProximityResult(
        features=[
            FeatureRecord(feature_id="f1", measure=100.0),
            FeatureRecord(feature_id="f2", measure=50.0),
        ]
    )
    assert result.feature_count == 2
    assert result.measure_value == 50.0  # nearest distance, not the count


def test_empty_adjacency_reports_zero():
    """An adjacency result with nothing adjacent sums to 0."""
    result = AdjacencyResult(is_adjacent=False, features=[])
    assert result.feature_count == 0
    assert result.measure_value == 0.0


def test_roundtrip_preserves_each_result_type():
    """A bundle holding all five result types survives JSON, and each one comes
    back as the right type with its measure intact (what operator_type is for)."""
    group = DatasetResultGroup(
        dataset_id="ds1",
        dataset_name="Mixed",
        results=[
            PolyOverlayResult(total_area=1500.5),
            LineOverlayResult(total_length=2000.0),
            PointOverlayResult(features=[
                FeatureRecord(feature_id="p1"), FeatureRecord(feature_id="p2"),
            ]),
            ProximityResult(features=[FeatureRecord(feature_id="f1", measure=50.0)]),
            AdjacencyResult(is_adjacent=True, features=[FeatureRecord(feature_id="n1", measure=10.0)]),
        ],
    )
    bundle = AstResults(job_id="j", aoi_id="aoi", results=[group])

    restored = AstResults.model_validate_json(bundle.model_dump_json())
    results = restored.results[0].results

    # each result keeps its type through the round-trip
    assert [type(r) for r in results] == [
        PolyOverlayResult, LineOverlayResult, PointOverlayResult,
        ProximityResult, AdjacencyResult,
    ]
    # and its headline measure is still correct
    assert [r.measure_value for r in results] == [1500.5, 2000.0, 2.0, 50.0, 10.0]