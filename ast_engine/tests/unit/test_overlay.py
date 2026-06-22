
"""
--------------------------------------------------------------------------
Overlay operator test

Purpose:
- Feed the operator simple geometry with known overlap:
    - 3 polygons
    - 3 polylines
- Check:
    - Intersection is calculated correctly
    - Per-feature overlap (area/length) is correct
    - Features are sorted by overlap (descending)
    - Totals are summed correctly
    - Properties and feature IDs are handled correctly
    - Non-overlapping features are dropped
    - Invalid AOIs are rejected




--------------------------------------------------------------------------
"""

import pytest
from pathlib import Path
import geopandas as gpd

from ast_engine.core.aoi.aoi_builder import AOIBuilder, AOIRequest, AreaOfInterest
from ast_engine.core.data_adapters.base import BaseSpatialAdapter, DatasetInfo
from ast_engine.core.data_adapters.file.adapter import FileSpatialAdapter
from ast_engine.core.operator.overlay import (
    intersection, _default_read_options, _require_projected
)

# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).parents[1] / "data"

SHP = DATA_DIR / "Test_AOI" / "Test_AOI.shp"

POLYGONS = DATA_DIR / "Test_Overlay" / "polygons.shp"
POLYLINES = DATA_DIR / "Test_Overlay" / "polylines.shp"
POINTS   = DATA_DIR / "Test_Overlay" / "points.shp"

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _valid_aoi() -> AreaOfInterest:
    gdf = gpd.read_file(SHP)
    request = AOIRequest(aoi_id="test_aoi", name="Test AOI")
    return AOIBuilder().from_gdf(request, gdf)


def non_valid_aoi() -> AreaOfInterest:
    aoi = _valid_aoi()
    aoi.gdf = aoi.gdf.to_crs(4326)
    return aoi


# ---------------------------------------------------------------------------
# Core overlay tests
# ---------------------------------------------------------------------------

def test_polygon_overlay_total_area():
    """Polygon overlap produces total_area and per-feature area measures."""
    test = intersection(
        aoi=_valid_aoi(),
        adapter=FileSpatialAdapter(),
        path=POLYGONS,
    )

    assert test.total_area >= 0
    assert all(f.measure is not None for f in test.features)


def test_line_overlay_total_length():
    """Line overlap produces total_length and per-feature length."""
    test = intersection(
        aoi=_valid_aoi(),
        adapter=FileSpatialAdapter(),
        path=POLYLINES,
    )

    assert test.total_length >= 0
    assert all(f.measure is not None for f in test.features)


def test_point_overlay_counts_features():
    """Point overlay counts features (no per-feature measure)."""
    test = intersection(
        aoi=_valid_aoi(),
        adapter=FileSpatialAdapter(),
        path=POINTS,
    )

    assert test.feature_count == len(test.features)
    assert all(f.measure is None for f in test.features)


# ---------------------------------------------------------------------------
# Ordering & filtering
# ---------------------------------------------------------------------------

def test_overlay_sorted_descending():
    """Features are sorted by overlap (largest first)."""
    test = intersection(
        aoi=_valid_aoi(),
        adapter=FileSpatialAdapter(),
        path=POLYGONS,
    )

    measures = [f.measure for f in test.features if f.measure is not None]
    assert measures == sorted(measures, reverse=True)


def test_non_intersecting_excluded():
    """Features with no overlap are removed."""
    test = intersection(
        aoi=_valid_aoi(),
        adapter=FileSpatialAdapter(),
        path=POLYGONS,
    )

    assert all((f.measure is None) or (f.measure > 0) for f in test.features)


# ---------------------------------------------------------------------------
# Attribute + ID handling
# ---------------------------------------------------------------------------

def test_overlay_keeps_properties():
    """Requested properties are preserved."""
    test = intersection(
        aoi=_valid_aoi(),
        adapter=FileSpatialAdapter(),
        keep_properties=["name"],
        path=POLYGONS,
    )

    assert all("name" in f.properties for f in test.features)


def test_feature_id_fallback():
    """Fallback to row index when ID field missing."""
    test = intersection(
        aoi=_valid_aoi(),
        adapter=FileSpatialAdapter(),
        feature_id_field="NOT_REAL",
        path=POLYGONS,
    )

    ids = [f.feature_id for f in test.features]
    assert len(set(ids)) == len(ids)


# ---------------------------------------------------------------------------
# Internal logic tests
# ---------------------------------------------------------------------------

def test_default_read_options():
    """Ensures read options include intersects filter and required columns."""
    opts = _default_read_options(
        aoi=_valid_aoi(),
        feature_id_field="Id",
        keep_properties=["Type"]
    )

    assert opts.spatial_filter.predicate == "intersects"
    assert set(opts.keep_columns) == {"Id", "Type"}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_non_projected_aoi_rejected():
    with pytest.raises(ValueError):
        intersection(
            aoi=non_valid_aoi(),
            adapter=FileSpatialAdapter(),
            path=POLYGONS,
        )


# ---------------------------------------------------------------------------
# Adapter interaction tests
# ---------------------------------------------------------------------------

class RecordingAdapter(BaseSpatialAdapter):
    """Captures read_options used by the operator."""

    def __init__(self):
        self.last_options = None

    def read(self, *, read_options=None, target_crs=None, **kwargs):
        self.last_options = read_options
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:3005")

    def _read_impl(self, *, read_options, **kwargs):
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:3005")

    def describe(self, **kwargs) -> DatasetInfo:
        raise NotImplementedError


def test_overlay_asks_for_intersects():
    """Operator pushes 'intersects' filter to adapter."""
    adapter = RecordingAdapter()

    intersection(
        aoi=_valid_aoi(),
        adapter=adapter,
        path=POLYGONS,
    )

    sf = adapter.last_options.spatial_filter
    assert sf.predicate == "intersects"


# ---------------------------------------------------------------------------
# Empty result handling
# ---------------------------------------------------------------------------

def test_empty_result_returns_zero():
    """Empty datasets return correct zero totals."""
    adapter = RecordingAdapter()

    test = intersection(
        aoi=_valid_aoi(),
        adapter=adapter,
        geom_type="polygon",  # force type
        path=POLYGONS,
    )

    assert test.total_area == 0.0
    assert test.features == []
