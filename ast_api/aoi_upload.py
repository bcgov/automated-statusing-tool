"""
Uploaded area of interest: file bytes in, GeoJSON out.

A job submitted with an uploaded file carries its area of interest onto the job
queue as GeoJSON. This module does the reading, at the API, so a file that
cannot be used is refused while the user is still looking at the form rather
than failing later in the worker.

The file is read with GeoPandas, the same reader the engine uses for its file
datasets, so the formats accepted here are ones the engine reads too.
"""

import json
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import geopandas as gpd

# File types accepted for an uploaded AOI, by extension.
ALLOWED_SUFFIXES = (".geojson", ".json", ".kml", ".kmz", ".gpkg", ".zip")

# The AOI travels as GeoJSON, which is longitude/latitude.
AOI_CRS = "EPSG:4326"

# The most a zip may unpack to. A zip is read in place, never extracted, but its
# shapefile is still decompressed in memory; this refuses a small file built to
# expand into a very large one.
MAX_UNZIPPED_BYTES = 200 * 1024 * 1024


class AoiUploadError(ValueError):
    """An uploaded file cannot be used as an area of interest.

    The message is returned to the browser, so it says what is wrong with the
    file and what to upload instead.
    """


def read_aoi_upload(filename: str | None, content: bytes) -> dict[str, Any]:
    """Read an uploaded spatial file into a GeoJSON FeatureCollection in EPSG:4326.

    filename  the name the browser sent. Only its extension is used, to tell the
              file type; the name itself never reaches the file system.
    content   the file's bytes.

    Only the geometry is kept. The engine dissolves the AOI into one shape, so
    the file's attributes are not used, and leaving them behind keeps whatever
    they hold off the job queue.

    Raises AoiUploadError when the file type is not accepted, the file cannot be
    read, it has no coordinate system, or it holds no shapes.
    """
    suffix = Path(filename or "").suffix.lower()
    if suffix == ".shp":
        # A shapefile is several files; the .shp alone has no coordinate system.
        raise AoiUploadError(
            "A shapefile must be uploaded as a .zip holding its .shp, .shx, .dbf and .prj files."
        )
    if suffix not in ALLOWED_SUFFIXES:
        raise AoiUploadError(
            f"Unsupported file type. Upload one of: {', '.join(ALLOWED_SUFFIXES)}."
        )

    # GDAL reads from a path and picks its driver from the extension, so the
    # bytes are written to a scratch file that keeps the extension only.
    with tempfile.TemporaryDirectory() as scratch:
        path = Path(scratch) / f"aoi{suffix}"
        path.write_bytes(content)
        source = _zipped_shapefile(path) if suffix == ".zip" else path
        try:
            gdf = gpd.read_file(source)
        except Exception as exc:
            raise AoiUploadError("The file could not be read as a spatial file.") from exc

    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty]
    if gdf.empty:
        raise AoiUploadError("The file holds no shapes.")
    if gdf.crs is None:
        raise AoiUploadError("The file has no coordinate system defined.")

    geometry_only = gdf[[gdf.geometry.name]].to_crs(AOI_CRS)
    return json.loads(geometry_only.to_json())


def _zipped_shapefile(path: Path) -> str:
    """Return the GDAL path of the shapefile inside an uploaded zip.

    People zip a shapefile two ways: the files on their own, or the folder they
    sit in. GDAL only finds the first by itself, so the .shp is located here and
    named outright ("zip://<zip>!<folder>/<name>.shp"), which covers both.

    The zip is only listed, not extracted, so the names inside it never become
    paths on disk.
    """
    try:
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
    except zipfile.BadZipFile as exc:
        raise AoiUploadError("The file could not be read as a zip file.") from exc

    if sum(member.file_size for member in members) > MAX_UNZIPPED_BYTES:
        raise AoiUploadError("The zip file is too large once unpacked.")

    shapefiles = [m.filename for m in members if m.filename.lower().endswith(".shp")]
    if len(shapefiles) != 1:
        raise AoiUploadError(
            "The zip file must hold exactly one shapefile (.shp, .shx, .dbf and .prj)."
        )
    return f"zip://{path}!{shapefiles[0]}"
