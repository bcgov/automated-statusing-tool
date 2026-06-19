from __future__ import annotations

import logging
import sys
from pathlib import Path

from shapely.geometry import Polygon, GeometryCollection, LineString, Point
import geopandas as gpd

ast_path = Path(__file__).resolve().parents[1]
ast_path_str = str(ast_path)

if ast_path_str not in sys.path:
    sys.path.append(ast_path_str)

from ast_engine.utils.logging_config import setup_logging
from ast_engine.core.data_adapters.base import ReadOptions
from ast_engine.core.data_adapters.file.adapter import FileSpatialAdapter
from ast_engine.core.aoi.models import AOIRequest, AOIBuildRequest
from ast_engine.core.aoi.aoi_builder import AOIBuilder
from ast_engine.core.aoi.exceptions import AOIBuildError, root_cause

PROJECTED_CRS = "EPSG:3005" 
UNPROJECTED_CRS = "EPSG:4326"

# ------------------------------------------------------------
# Data scenarios
# ------------------------------------------------------------

def load_kmz_example() -> gpd.GeoDataFrame:
    opts = ReadOptions(keep_columns=["Name"])
    return FileSpatialAdapter().read(
        path="ast_engine/tests/data/Test_Shape_A/Test_Shape_A.kmz",
        target_crs=PROJECTED_CRS,
        read_options=opts,
    )

def load_gj_example() -> gpd.GeoDataFrame:
    opts = ReadOptions(keep_columns=["Name"])
    return FileSpatialAdapter().read(
        path="ast_engine/tests/data/Test_Shape_A/Test_Shape_A.geojson",
        target_crs=PROJECTED_CRS,
        read_options=opts,
    )

def load_kml_example() -> gpd.GeoDataFrame:
    opts = ReadOptions(keep_columns=["Name"])
    return FileSpatialAdapter().read(
        path="ast_engine/tests/data/Test_Shape_A/Test_Shape_A.kml",
        target_crs=PROJECTED_CRS,
        read_options=opts,
    )

def load_gpkg_example() -> gpd.GeoDataFrame:
    opts = ReadOptions(keep_columns=["Name"])
    return FileSpatialAdapter().read(
        path="ast_engine/tests/data/Test_Shape_A/Test_Shape_A.gpkg",
        target_crs=PROJECTED_CRS,
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
        crs=PROJECTED_CRS,
    )

def load_small_area_groups_example() -> gpd.GeoDataFrame:
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
        crs=PROJECTED_CRS,
    )


def load_large_area_groups_example() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "group_id": ["A", "A", "B", "B", "B", "C", "C"],
        },
        geometry=[
            # Group A
            Polygon([(0, 0), (11000, 0), (11000, 11000), (0, 11000), (0, 0)]),
            Polygon([(8000, 8000), (19000, 8000), (19000, 19000), (8000, 19000), (8000, 8000)]),

            # Group B
            Polygon(None),
            Polygon([(25000, 0), (36000, 0), (36000, 11000), (25000, 11000), (25000, 0)]),
            Polygon([(32000, 4000), (43000, 4000), (43000, 15000), (32000, 15000), (32000, 4000)]),

            # Group C
            Polygon([(50000, 0), (61000, 0), (61000, 11000), (50000, 11000), (50000, 0)]),
            Polygon([(59000, 5000), (70000, 5000), (70000, 16000), (59000, 16000), (59000, 5000)]),
        ],
        crs=PROJECTED_CRS,
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
        crs=PROJECTED_CRS,
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
        crs=PROJECTED_CRS,
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
        crs=PROJECTED_CRS,
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
        "geojson": load_gj_example,
        "kml": load_kml_example,
        "gpkg": load_gpkg_example,
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
        target_crs=PROJECTED_CRS,
        dissolve_mode="full_union",
        allow_overlaps=False,
    )


def request_by_name_overlap_allowed() -> AOIRequest:
    return AOIRequest(
        aoi_id="aoi_002",
        name="Test AOI",
        target_crs=PROJECTED_CRS,
        dissolve_mode="by_fields",
        dissolve_fields=("Name",),
        allow_overlaps=True,
    )


def request_by_group_overlap_allowed() -> AOIRequest:
    return AOIRequest(
        aoi_id="aoi_003",
        name="Test AOI",
        target_crs=PROJECTED_CRS,
        dissolve_mode="by_fields",
        dissolve_fields=("group_id",),
        allow_overlaps=True,
    )

def request_by_group_overlap_not_allowed() -> AOIRequest:
    return AOIRequest(
        aoi_id="aoi_004",
        name="Test AOI",
        target_crs=PROJECTED_CRS,
        dissolve_mode="by_fields",
        dissolve_fields=("group_id",),
        allow_overlaps=False,
    )

def request_preserve_features() -> AOIRequest:
    return AOIRequest(
        aoi_id="aoi_005",
        name="Test AOI",
        target_crs=PROJECTED_CRS,
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

    built = AOIBuildRequest(
        spec=request,
        raw_gdf=raw_gdf,
    )

    builder = AOIBuilder()

    print("")
    logger.info(
        "=== DATA CASE: %s | REQUEST CASE: %s ===",
        data_case,
        request_case,
    )
    logger.info("Columns: %s", list(raw_gdf.columns))
    logger.info("CRS: %s", raw_gdf.crs.name if raw_gdf.crs else None)
    logger.info("Geom types: %s", raw_gdf.geometry.geom_type.tolist())

    try:
        aoi_result = builder.build_from_request(
            built,
        )

        aoi = aoi_result.aoi

        if aoi_result.is_valid:
            logger.info("STATUS: SUCCESS")
        else:
            logger.warning("STATUS: FAILED")

        if aoi_result.errors:
            logger.info("Errors:")
            for issue in aoi_result.errors:
                logger.error("  - %s: %s", issue.code, issue.message)

        if aoi_result.warnings:
            logger.info("Warnings:")
            for issue in aoi_result.warnings:
                logger.warning("  - %s: %s", issue.code, issue.message)

        logger.info("ID: %s", aoi.aoi_id)
        logger.info("Columns: %s", list(aoi.gdf.columns))
        logger.info("Footprint Area (ha): %.4f", aoi.footprint_area_ha)
        logger.info("Bounds: %s", aoi.bounds)
        logger.info("Part Count: %s", len(aoi.parts))

    except AOIBuildError as exc:
        root = root_cause(exc)

        logger.error(
            "STATUS: FAILED | reason=%s",
            root,
        )

        logger.debug(
            "Failure root traceback",
            exc_info=(type(root), root, root.__traceback__),
        )


def log_normalization_report(aoi) -> None:
    r = getattr(aoi, "normalized", None)

    if r is None:
        logger.warning("Normalization report: unavailable")
        return

    logger.info(
        "Normalization features: %s input → %s cleaned → %s output",
        r.input_feature_count,
        r.cleaned_feature_count,
        r.output_feature_count,
    )

    logger.info(
        "Normalization CRS: %s → %s | reprojected=%s",
        r.input_crs,
        r.output_crs,
        r.was_reprojected,
    )

    logger.info(
        "Geometry cleanup: null/empty removed=%s | repaired=%s of %s",
        r.null_or_empty_removed_count,
        r.repaired_feature_count,
        r.repair_input_feature_count,
    )

    logger.info(
        "Polygon extraction: %s components in | %s polygon components kept | %s non-polygon components dropped",
        r.polygon_extract_input_feature_count,
        r.polygon_extract_output_feature_count,
        r.polygon_extract_drop_count,
    )

    logger.info(
        "AOI policy: mode=%s | dissolve_fields=%s | allow_overlaps=%s",
        r.policy_name,
        format_tuple(r.dissolve_fields_used),
        r.allow_overlaps,
    )

    logger.info(
        "AOI policy features: %s input → %s output",
        r.policy_input_feature_count,
        r.policy_output_feature_count,
    )

    logger.info(
        "Overlaps: before=%s | after=%s | resolved=%s",
        r.overlaps_detected_before_policy,
        r.overlaps_present_after_policy,
        r.overlaps_resolved_by_policy,
    )

    for note in r.notes:
        logger.info("Normalization note: %s", note)

def format_tuple(values: tuple[str, ...]) -> str:
    if not values:
        return "<none>"

    return ", ".join(values)


if __name__ == "__main__":
    setup_logging()

    logger = logging.getLogger(__name__)

    logger.info("Beginning AOI builder demo")

    scenarios = [
        ("kmz", "by_name_overlap_allowed"),
        ("geojson", "by_name_overlap_allowed"),
        ("gpkg", "by_name_overlap_allowed"),
        ("kml", "by_name_overlap_allowed"),
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
    
    print("")
    logger.info("End of AOI builder demo")