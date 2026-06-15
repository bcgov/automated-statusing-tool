"""
FileSpatialAdapter
Reads spatial features from a local file and returns a GeoDataFrame.

Handles every GDAL supported file format the AST takes as input: shapefile,
file geodatabase, GeoPackage, GeoJSON, KML and KMZ. They are all read through
gpd.read_file(): GDAL picks the right driver from the file extension, so one
adapter covers them all.
"""

import re
from pathlib import Path

import geopandas as gpd
import pyogrio

from ..base import BaseSpatialAdapter, DatasetInfo, ReadOptions, SpatialFilter
from ..exceptions import DataReadError


# Container formats that hold named layers. The datasource string tacks the
# layer name on after the container (e.g. ".../foo.gdb/roads"); the lookahead
# matches the extension only when it is a whole path segment (followed by a
# slash or the end of the string), so file names that merely contain the text
# are not split by accident.
_CONTAINER_RE = re.compile(r"\.(gdb|gpkg)(?=[\\/]|$)", re.IGNORECASE)


def _split_datasource(datasource: str | Path) -> tuple[str, str | None]:
    """Split a datasource string into a file path and an optional layer name.

    The registry stores a dataset's location as one string. For container
    formats the layer is tacked on after the container:
        W:/data/foo.gdb/roads              -> ("W:/data/foo.gdb", "roads")
        \\\\server\\share\\foo.gpkg\\lakes -> ("\\\\server\\share\\foo.gpkg", "lakes")

    A file geodatabase may keep a feature class inside a feature dataset; GDAL
    addresses the layer by the feature class name alone, so only the last
    segment is the layer:
        W:/data/foo.gdb/dataset/roads      -> ("W:/data/foo.gdb", "roads")

    A container with nothing after it has no named layer (GDAL reads the
    default / only layer):
        W:/data/foo.gdb                    -> ("W:/data/foo.gdb", None)
        
    Flat formats (shapefile, GeoJSON, KML, KMZ) are the whole string, no layer:
        C:/data/bar.shp                -> ("C:/data/bar.shp", None)

    The split is on the container extension (.gdb / .gpkg), not on slashes, so
    drive letters (W:), UNC paths (\\\\server\\share) and mixed forward / back
    slashes all work.
    """
    text = str(datasource)
    match = _CONTAINER_RE.search(text)
    if match is None:
        # flat file - the whole string is the path
        return text, None

    path = text[: match.end()]
    segments = [s for s in re.split(r"[\\/]+", text[match.end():]) if s]
    layer = segments[-1] if segments else None
    return path, layer


def _normalize_geometry_type(name: str | None) -> str | None:
    """Collapse a GDAL geometry-type name to point, line or polygon.

    GDAL reports names like "Point", "MultiPolygon" or "LineString", sometimes
    with a 3D suffix ("Polygon Z"). Multipart and 3D variants collapse to the
    same single-part name. Returns None when GDAL cannot report a concrete type
    ("Unknown", common for KML) or for types AST does not handle.
    """
    if not name:
        return None
    text = name.lower()
    if "point" in text:
        return "point"
    if "polygon" in text or "surface" in text:
        return "polygon"
    if "line" in text or "curve" in text or "string" in text:
        return "line"
    return None


class FileSpatialAdapter(BaseSpatialAdapter):
    """Adapter for local spatial files (SHP, FGDB, GeoPackage, GeoJSON, KML, KMZ).

    `path` is the dataset's full location as stored in the registry. For
    container formats that hold more than one layer (file geodatabase,
    GeoPackage) the layer name is part of that string, after the container
    (".../foo.gdb/roads"); the adapter splits it out. Flat files like shapefile
    and GeoJSON are just the path, no layer.

    When ReadOptions carries a SpatialFilter, the AOI bounding box is pushed
    down to gpd.read_file() so GDAL only returns features near the AOI instead
    of reading the whole file (much more efficient). The push-down is a coarse
    pre-filter (bounding box level) - the operator still does the exact spatial
    test afterwards.
    """

    def _read_impl(
        self,
        *,
        path: str | Path,
        read_options: ReadOptions,
        **_,
    ) -> gpd.GeoDataFrame:
        """Read the file, pushing the AOI bounding box down to GDAL."""
        file_path, layer = _split_datasource(path)
        bbox = self._build_bbox(read_options.spatial_filter)
        try:
            gdf = gpd.read_file(file_path, layer=layer, bbox=bbox)
        except Exception as exc:
            raise DataReadError(f"Failed to read spatial file: {path}") from exc
        return gdf

    def describe(self, *, path: str | Path, **_) -> DatasetInfo:
        """Return the file's metadata without reading all of its features.

        Reads the layer information (geometry type, CRS, fields, feature count)
        with pyogrio - this does not load the features themselves. For KML / KMZ
        GDAL often cannot report a geometry type from the layer header
        ("Unknown"); in that case a single feature is read to find the type.
        """
        file_path, layer = _split_datasource(path)
        try:
            info = pyogrio.read_info(file_path, layer=layer)
        except Exception as exc:
            raise DataReadError(f"Failed to inspect spatial file: {path}") from exc

        crs = info.get("crs")
        if not crs:
            raise DataReadError(f"Spatial file has no CRS defined: {path}")

        geometry_type = _normalize_geometry_type(info.get("geometry_type"))
        if geometry_type is None:
            geometry_type = self._geometry_type_from_sample(file_path, layer)

        # geometry_name is empty for flat formats (shapefile, GeoJSON, KML);
        # those read back as a "geometry" column, so report that name.
        geom_column = info.get("geometry_name") or "geometry"

        features = info.get("features")
        row_count = int(features) if features is not None and features >= 0 else None

        return DatasetInfo(
            geom_column=geom_column,
            crs=str(crs),
            geometry_type=geometry_type,
            columns=list(info.get("fields", [])),
            row_count=row_count,
        )

    def _geometry_type_from_sample(
        self,
        file_path: str | Path,
        layer: str | None,
    ) -> str:
        """Determine the geometry type by reading a single feature.

        Used when GDAL cannot report the type from the layer header (e.g.
        KML / KMZ, which report "Unknown"). Reading one feature is enough and
        avoids loading the whole file.
        """
        try:
            sample = pyogrio.read_dataframe(file_path, layer=layer, max_features=1)
        except Exception as exc:
            raise DataReadError(
                f"Failed to read a sample feature to determine geometry type: {file_path}"
            ) from exc
        if sample.empty:
            raise DataReadError(
                f"Cannot determine geometry type - file has no features: {file_path}"
            )
        raw = sample.geom_type.iloc[0]
        geometry_type = _normalize_geometry_type(raw)
        if geometry_type is None:
            raise DataReadError(
                f"Unsupported geometry type {raw!r} in {file_path}"
            )
        return geometry_type

    def _build_bbox(
        self,
        spatial_filter: SpatialFilter | None,
    ) -> gpd.GeoSeries | None:
        """Turn a SpatialFilter into a bounding box for gpd.read_file().

        Returned as a GeoSeries (carries its CRS) so geopandas reprojects
        it to the dataset's CRS before filtering. Returns None when there is
        nothing to push down.

        bbox creation is predicate dependent:
          - intersects / touches -> the AOI itself
          - within_distance      -> the AOI buffered by the search distance,
                                    so features just outside the AOI are kept
          - nearest              -> no filter. the closest feature can be
                                    anywhere, so the whole file is read
        """
        if spatial_filter is None or spatial_filter.predicate == "nearest":
            return None

        if spatial_filter.predicate == "within_distance":
            aoi = spatial_filter.aoi
            if not aoi.crs.is_projected:
                raise DataReadError(
                    "within_distance push-down needs a projected AOI CRS "
                    "(the search distance is measured in metres)"
                )
            return aoi.buffer(spatial_filter.distance)

        # intersects / touches
        return spatial_filter.aoi.geometry
