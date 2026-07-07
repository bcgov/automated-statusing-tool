# tests/helpers/aoi_requests.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ast_engine.core.aoi.models import AOIBuildRequest, AOIRequest

PROJECTED_CRS = "EPSG:3005"
UNPROJECTED_CRS = "EPSG:4326"


def make_aoi_request(
    *,
    aoi_id: str = "test_aoi",
    name: str = "Test AOI",
    target_crs: str = PROJECTED_CRS,
    dissolve_mode: str = "full_union",
    dissolve_fields: tuple[str, ...] = (),
    allow_overlaps: bool = False,
    **overrides: Any,
) -> AOIRequest:
    """
    Generic AOIRequest factory for tests.

    Use this when a test needs a small variation from the default request.
    Prefer the named helpers below for common request types.
    """
    values = {
        "aoi_id": aoi_id,
        "name": name,
        "target_crs": target_crs,
        "dissolve_mode": dissolve_mode,
        "dissolve_fields": dissolve_fields,
        "allow_overlaps": allow_overlaps,
    }

    values.update(overrides)

    return AOIRequest(**values)


def full_union_request(
    *,
    allow_overlaps: bool = False,
) -> AOIRequest:
    return make_aoi_request(
        dissolve_mode="full_union",
        dissolve_fields=(),
        allow_overlaps=allow_overlaps,
    )


def by_group_request(
    *,
    allow_overlaps: bool = True,
) -> AOIRequest:
    return make_aoi_request(
        dissolve_mode="by_fields",
        dissolve_fields=("group_id",),
        allow_overlaps=allow_overlaps,
    )


def by_name_request(
    *,
    allow_overlaps: bool = True,
) -> AOIRequest:
    return make_aoi_request(
        dissolve_mode="by_fields",
        dissolve_fields=("Name",),
        allow_overlaps=allow_overlaps,
    )


def preserve_features_request(
    *,
    allow_overlaps: bool = True,
) -> AOIRequest:
    return make_aoi_request(
        dissolve_mode="preserve_features",
        dissolve_fields=(),
        allow_overlaps=allow_overlaps,
    )


def unprojected_target_crs_request() -> AOIRequest:
    """
    Request with an unprojected target CRS.

    Useful for tests that confirm the AOI system rejects unsuitable target CRS values.
    """
    return make_aoi_request(
        target_crs=UNPROJECTED_CRS,
    )


def by_missing_field_request() -> AOIRequest:
    """
    Request that references a dissolve field not present in common test GeoDataFrames.
    """
    return make_aoi_request(
        dissolve_mode="by_fields",
        dissolve_fields=("missing_field",),
        allow_overlaps=True,
    )


def by_empty_fields_request() -> AOIRequest:
    """
    Request with by_fields mode but no dissolve fields.

    Useful if your AOIRequest allows construction but the builder/policy should reject it.
    """
    return make_aoi_request(
        dissolve_mode="by_fields",
        dissolve_fields=(),
        allow_overlaps=True,
    )


def build_aoi_request(
    *,
    raw_gdf,
    spec: AOIRequest | None = None,
) -> AOIBuildRequest:
    return AOIBuildRequest(
        spec=spec or full_union_request(),
        raw_gdf=raw_gdf,
    )