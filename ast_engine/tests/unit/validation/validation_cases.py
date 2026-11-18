"""Small builders for validation tests. No test depends on another test module."""

from pathlib import Path

import geopandas as gpd
import yaml

from ast_engine.core.aoi import AOIBuildRequest, AOIRequest
from ast_engine.core.validation.geometry.models import GeometryConfig
from ast_engine.core.validation.spatial.models import SpatialLayerReferenceConfig

CRS = "EPSG:3005"
UNITS = ("file", "units.gpkg")


def frame(*geometries, crs=CRS, **columns):
    return gpd.GeoDataFrame(columns, geometry=list(geometries), crs=crs)


def rule(check="min_area", *, rule_id="minimum_part_area", scope="part", severity="error", **options):
    return {"id": rule_id.upper(), "check": check, "scope": scope, "severity": severity, **options}


def geometry_policy(*rules):
    return GeometryConfig.model_validate({"rules": list(rules)})


def layer_doc(name="units", *, datasource="units.gpkg", scope="footprint", rules=None, **options):
    return {
        "name": name,
        "datasource": datasource,
        "data_adapter": "file",
        "scope": scope,
        "rules": {"no_overlap": "error"} if rules is None else rules,
        **options,
    }


def layer(*args, **kwargs):
    return SpatialLayerReferenceConfig.model_validate(layer_doc(*args, **kwargs))


def build(builder, *geometries, parameters=None, aoi_id="parcel", **request_options):
    spec = AOIRequest(
        aoi_id=aoi_id, name="Test parcel", validation_parameters=parameters, **request_options
    )
    return builder.build_from_request(AOIBuildRequest(spec=spec, raw_gdf=frame(*geometries)))


def write_policy(path: Path, document: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path
