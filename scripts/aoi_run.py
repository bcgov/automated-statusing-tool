from py_compile import main
import sys
from pathlib import Path

from shapely.geometry import Polygon, GeometryCollection, LineString, Point
import geopandas as gpd

sys.path.append(str(Path(__file__).parents[1]))

from ast.core.data_adapters.base import ReadOptions
from ast.core.data_adapters.kml.adapter import KMLAdapter
from ast.core.aoi.models import AOIRequest
from ast.core.aoi.aoi_builder import AOIBuilder



# ------------------------------------------------------------
# Data scenarios
# ------------------------------------------------------------

def load_kmz_example() -> gpd.GeoDataFrame:
    opts = ReadOptions(keep_columns=["Name"])
    return KMLAdapter().read(
        path="ast_app/Test_Shape_A/Test_Shape_A.kmz",
        target_crs="EPSG:3005",
        read_options=opts,
    )


def load_overlap_groups_example() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "group_id": ["A", "A", "A", "B", "B", "C", "C"],
        },
        geometry=[
            # Group A
            Polygon(None), # Empty geometry; should be dropped and trigger validation error for no valid geometry
            Polygon([(0, 0), (100, 0), (100, 100), (0, 100), (0, 0)]),
            Polygon([(80, 80), (180, 80), (180, 180), (80, 180), (80, 80)]),

            # Group B
            Polygon([(250, 0), (350, 0), (350, 100), (250, 100), (250, 0)]),
            Polygon([(320, 40), (420, 40), (420, 140), (320, 140), (320, 40)]),

            # Group C
            Polygon([(275, 0), (375, 0), (375, 100), (275, 100), (275, 0)]),
            Polygon([(370, 50), (470, 50), (470, 190), (370, 190), (370, 50)]),
        ],
        crs="EPSG:3005",
    )

def load_small_area_groups_example() -> gpd.GeoDataFrame:
    """
    Each polygon is 20 m x 20 m = 400 m² = 0.04 ha (< 0.1 ha)
    """
    return gpd.GeoDataFrame(
        {
            "group_id": ["A", "A", "B", "B", "C", "C"],
        },
        geometry=[
            # Group A
            Polygon([(0, 0), (20, 0), (20, 20), (0, 20), (0, 0)]),
            Polygon([(10, 10), (30, 10), (30, 30), (10, 30), (10, 10)]),

            # Group B
            Polygon([(50, 0), (70, 0), (70, 20), (50, 20), (50, 0)]),
            Polygon([(60, 8), (80, 8), (80, 28), (60, 28), (60, 8)]),

            # Group C
            Polygon([(100, 0), (120, 0), (120, 20), (100, 20), (100, 0)]),
            Polygon([(115, 5), (135, 5), (135, 25), (115, 25), (115, 5)]),
        ],
        crs="EPSG:3005",
    )


def load_large_area_groups_example() -> gpd.GeoDataFrame:
    """
    Each polygon is 11,000 m x 11,000 m = 121,000,000 m² = 12,100 ha (> 10,000 ha)
    """
    return gpd.GeoDataFrame(
        {
            "group_id": ["A", "A", "B", "B", "C", "C"],
        },
        geometry=[
            # Group A
            Polygon([(0, 0), (11000, 0), (11000, 11000), (0, 11000), (0, 0)]),
            Polygon([(8000, 8000), (19000, 8000), (19000, 19000), (8000, 19000), (8000, 8000)]),

            # Group B
            Polygon([(25000, 0), (36000, 0), (36000, 11000), (25000, 11000), (25000, 0)]),
            Polygon([(32000, 4000), (43000, 4000), (43000, 15000), (32000, 15000), (32000, 4000)]),

            # Group C
            Polygon([(50000, 0), (61000, 0), (61000, 11000), (50000, 11000), (50000, 0)]),
            Polygon([(59000, 5000), (70000, 5000), (70000, 16000), (59000, 16000), (59000, 5000)]),
        ],
        crs="EPSG:3005",
    )

def load_bowtie_example() -> gpd.GeoDataFrame:
    # Self-intersecting polygon
    bowtie = Polygon([
        (0, 0),
        (100, 100),
        (0, 100),
        (100, 0),
        (0, 0),
    ])
    return gpd.GeoDataFrame(
        {"group_id": ["A"]},
        geometry=[bowtie],
        crs="EPSG:3005",
    )


def load_gc_polygon_line_example() -> gpd.GeoDataFrame:
    # GeometryCollection containing polygon + line; should pass but drop line
    gc = GeometryCollection([
        Polygon([(0, 0), (100, 0), (100, 100), (0, 100), (0, 0)]),
        LineString([(0, 0), (100, 100)]),
    ])
    return gpd.GeoDataFrame(
        {"group_id": ["A"]},
        geometry=[gc],
        crs="EPSG:3005",
    )


def load_gc_line_point_example() -> gpd.GeoDataFrame:
    # GeometryCollection with no polygonal content; should fail
    gc = GeometryCollection([
        LineString([(0, 0), (100, 100)]),
        Point(50, 50),
    ])
    return gpd.GeoDataFrame(
        {"group_id": ["A"]},
        geometry=[gc],
        crs="EPSG:3005",
    )


def load_missing_crs_example() -> gpd.GeoDataFrame:
    # Missing CRS; should fail
    poly = Polygon([(0, 0), (100, 0), (100, 100), (0, 100), (0, 0)])
    return gpd.GeoDataFrame(
        {"group_id": ["A"]},
        geometry=[poly],
    )



def load_raw_gdf(case_name: str) -> gpd.GeoDataFrame:
    cases = {
        "kmz": load_kmz_example,
        "overlap_groups": load_overlap_groups_example,
        "small_area": load_small_area_groups_example,
        "large_area": load_large_area_groups_example,
        "bowtie": load_bowtie_example,
        "gc_polygon_line": load_gc_polygon_line_example,
        "gc_line_point": load_gc_line_point_example,
        "missing_crs": load_missing_crs_example,
    }

    try:
        return cases[case_name]()
    except KeyError as exc:
        raise ValueError(f"Unknown data case: {case_name!r}. Choose from {list(cases)}") from exc


# ------------------------------------------------------------
# Request scenarios
# ------------------------------------------------------------

def request_full_union() -> AOIRequest:
    return AOIRequest(
        aoi_id="aoi_001",
        name="Test AOI",
        target_crs="EPSG:3005",
        dissolve_mode="full_union",
        allow_overlaps=False,
    )


def request_by_name_overlap_allowed() -> AOIRequest:
    return AOIRequest(
        aoi_id="aoi_001",
        name="Test AOI",
        target_crs="EPSG:3005",
        dissolve_mode="by_fields",
        dissolve_fields=("Name",),
        allow_overlaps=True,
    )


def request_by_group_overlap_allowed() -> AOIRequest:
    return AOIRequest(
        aoi_id="aoi_001",
        name="Test AOI",
        target_crs="EPSG:3005",
        dissolve_mode="by_fields",
        dissolve_fields=("group_id",),
        allow_overlaps=True,
    )

def request_by_group_overlap_not_allowed() -> AOIRequest:
    return AOIRequest(
        aoi_id="aoi_001",
        name="Test AOI",
        target_crs="EPSG:3005",
        dissolve_mode="by_fields",
        dissolve_fields=("group_id",),
        allow_overlaps=False,
    )

def request_preserve_features() -> AOIRequest:
    return AOIRequest(
        aoi_id="aoi_001",
        name="Test AOI",
        target_crs="EPSG:3005",
        dissolve_mode="preserve_features",
        allow_overlaps=True,
    )


def build_request(case_name: str) -> AOIRequest:
    cases = {
        "full_union": request_full_union,
        "by_name_overlap_allowed": request_by_name_overlap_allowed,
        "by_group_overlap_allowed": request_by_group_overlap_allowed,
        "by_group_overlap_not_allowed": request_by_group_overlap_not_allowed,
        "preserve_features": request_preserve_features,
    }

    try:
        return cases[case_name]()
    except KeyError as exc:
        raise ValueError(f"Unknown request case: {case_name!r}. Choose from {list(cases)}") from exc

# ------------------------------------------------------------
# Demo runner
# ------------------------------------------------------------

def run_demo(data_case: str, request_case: str) -> None:
    raw_gdf = load_raw_gdf(data_case)
    request = build_request(request_case)

    builder = AOIBuilder()

    print(f"\n=== DATA CASE: {data_case} | REQUEST CASE: {request_case} ===")
    print("Columns:", list(raw_gdf.columns))
    print("CRS:", raw_gdf.crs)
    print("Geom types:", raw_gdf.geometry.geom_type.tolist())

    try:
        aoi = builder.from_gdf(
            request,
            raw_gdf,
            raise_errors=False,
        )

        if aoi.validation.is_valid:
            print("STATUS: SUCCESS")
        else:
            print("STATUS: FAILED")

        errors = [i for i in aoi.validation.issues if i.severity.lower() == "error"]
        warnings = [i for i in aoi.validation.issues if i.severity.lower() == "warning"]

        if errors:
            print("Errors:")
            for issue in errors:
                print(f"  - {issue.code}: {issue.message}")

        if warnings:
            print("Warnings:")
            for issue in warnings:
                print(f"  - {issue.code}: {issue.message}")

        print("ID:", aoi.aoi_id)
        print("Footprint Area (ha):", round(aoi.footprint_area_ha, 4))
        print("Bounds:", aoi.bounds)
        print("Part Count:", len(aoi.parts))

        if aoi.normalization_report:
            r = aoi.normalization_report
            print("Normalization:")
            print("  Input features:", r.input_feature_count)
            print("  Cleaned features:", r.cleaned_feature_count)
            print("  Output features:", r.output_feature_count)
            print("  Null feature drops:", r.null_or_empty_removed_count)

            print("  Repair step:")
            print("    Input features:", r.repair_input_feature_count)
            print("    Repaired features:", r.repaired_feature_count)

            print("  Polygon filter step:")
            print("    Input features:", r.polygon_extract_input_feature_count)
            print("    Output features:", r.polygon_extract_output_feature_count)
            print("    Dropped features:", r.polygon_extract_drop_count)

            print("  Overlap policy:")
            print("    Overlaps before policy:", r.overlaps_detected_before_policy)
            print("    Overlaps after policy:", r.overlaps_present_after_policy)
            print("    Overlaps resolved:", r.overlaps_resolved_by_policy)

            if r.notes:
                print("  notes:")
                for note in r.notes:
                    print(f"    - {note}")

    except Exception as exc:
        print("STATUS: FAILED")
        print(type(exc).__name__, "-", exc)


if __name__ == "__main__":
    scenarios = [
        ("kmz", "by_name_overlap_allowed"),
        ("overlap_groups", "full_union"),
        ("overlap_groups", "by_group_overlap_allowed"),
        ("overlap_groups", "by_group_overlap_not_allowed"),
        ("small_area", "by_group_overlap_allowed"),
        ("large_area", "by_group_overlap_allowed"),
        ("bowtie", "full_union"),
        ("gc_polygon_line", "full_union"),
        ("gc_line_point", "full_union"),
        ("missing_crs", "full_union"),
    ]

    for data_case, request_case in scenarios:
        run_demo(data_case, request_case)