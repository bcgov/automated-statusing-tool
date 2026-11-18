"""
Job builder: queue message -> a job the worker can run.

The API puts a small JobQueueItem on the queue: who asked, which region, and
where the area of interest comes from. The worker runs an AstJob, which needs
the things themselves - the registries to analyse and the AOI as a shape. This
module does that step, the only place that knows both forms:

  - registries: the datasets to analyse are chosen by the job's region, and
    loaded from the registry folder the spreadsheet ingestion writes to;
  - AOI: either the shape the API read out of an uploaded file, or a TANTALIS
    parcel looked up in BCGW from its three identifiers.

A request that cannot be turned into a job raises JobRequestError, whose message
is written for the person who submitted the job.
"""

import json
import logging
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

import geopandas as gpd

from ast_engine.config.registry import utils
from ast_engine.config.registry.models import Registry
from ast_engine.core.data_adapters.exceptions import DataReadError
from ast_engine.core.data_adapters.oracle import OracleConnection, fetch_tantalis_aoi
from ast_engine.entry.worker import AstJob, JobStatus
from shared_models.models import JobQueueItem, SOURCE_TANTALIS

logger = logging.getLogger(__name__)

# Registry file names, without the .yaml. They are the names of the statusing
# input spreadsheets they are built from, so a registry folder produced by the
# spreadsheet ingestion works as it is.
COMMON_REGISTRY = "one_status_common_datasets"
REGION_REGISTRY = "one_status_{region}_specific"
# Tab 1 is hand-written, not built from a spreadsheet (config/registry/tab1).
TAB1_REGISTRY = "tab1"

# The AOI travels as GeoJSON, which is longitude/latitude.
AOI_CRS = "EPSG:4326"


class JobRequestError(Exception):
    """A queued job cannot be run as it was submitted.

    The message is shown to the person who submitted the job, so it says what
    is wrong in their terms and carries no internal detail.
    """


def normalize_region(region: str) -> str:
    """Turn a region name into the form used in registry file names.

    "Kootenay Boundary" -> "kootenay_boundary". The same rule the ArcGIS Pro
    tool uses to pick its regional spreadsheet.
    """
    return region.strip().replace(" ", "_").lower()


def load_registries(
    region: str,
    registry_dir: str | Path | None,
    suppress_tab3: bool = False,
) -> list[tuple[str, Registry]]:
    """Load the registries one job runs against, in order: the common datasets,
    the region's own datasets, then Tab 1.

    With suppress_tab3 only Tab 1 is loaded: the common and regional datasets
    are what the Conflicts & Constraints tab is made from, so a job that leaves
    that tab out has no use for them.

    The common registry is required - a run without it would report nothing for
    the datasets every status covers. The regional registry and Tab 1 are used
    when their file is in the folder and skipped, with a warning, when it is
    not, so a folder that only holds some of them still runs.

    Each item is a (name, Registry) pair, the form build_tasks takes; the name
    is recorded on every result as the registry it came from.
    """
    if not registry_dir:
        raise FileNotFoundError(
            "No registry folder is configured; set registry_output_path to the "
            "folder holding the registry yaml files."
        )
    folder = Path(registry_dir)

    # The registry a job cannot do without: the one its main tab is made from.
    if suppress_tab3:
        names, required = [TAB1_REGISTRY], TAB1_REGISTRY
    else:
        names = [COMMON_REGISTRY, REGION_REGISTRY.format(region=normalize_region(region)), TAB1_REGISTRY]
        required = COMMON_REGISTRY
    registries: list[tuple[str, Registry]] = []
    for name in names:
        path = folder / f"{name}.yaml"
        if not path.is_file():
            if name == required:
                label = "common" if name == COMMON_REGISTRY else "Tab 1"
                raise FileNotFoundError(f"The {label} registry was not found: {path}")
            logger.warning("Registry %s not found in %s; running without it", name, folder)
            continue
        registries.append((name, utils.load_yaml(path)))
    return registries


def resolve_aoi(item: JobQueueItem, oracle_connection: Optional[OracleConnection]) -> dict[str, Any]:
    """Return the job's area of interest as a GeoJSON FeatureCollection in EPSG:4326.

    An upload job already carries its shape. A TANTALIS job carries the parcel's
    three identifiers, and the parcel is read from BCGW here.
    """
    if item.source != SOURCE_TANTALIS:
        if not item.aoi or not item.aoi.get("features"):
            raise JobRequestError("The job has no area of interest to analyse.")
        return item.aoi

    if oracle_connection is None:
        raise JobRequestError(
            "A TANTALIS lookup needs a BCGW connection, and this worker has none configured."
        )
    try:
        gdf = fetch_tantalis_aoi(
            oracle_connection.connection,
            oracle_connection.cursor,
            item.crown_file_number,
            item.disposition_number,
            item.parcel_number,
        )
    except DataReadError as exc:
        # Raised when no parcel matches the three identifiers, which is the
        # user's to fix. The message names only the identifiers they typed.
        raise JobRequestError(str(exc)) from exc
    return _to_geojson(gdf)


def _to_geojson(gdf: gpd.GeoDataFrame) -> dict[str, Any]:
    """A GeoDataFrame's geometry as a GeoJSON FeatureCollection in EPSG:4326.

    Only the geometry is kept: the run dissolves the AOI into one shape, so the
    attributes are not used, and dropping them keeps dates and other values that
    do not fit JSON out of the way.
    """
    geometry_only = gdf[[gdf.geometry.name]].to_crs(AOI_CRS)
    return json.loads(geometry_only.to_json())


def _aoi_name(item: JobQueueItem) -> str:
    """A readable name for the job's AOI, for the logs and the results."""
    if item.source == SOURCE_TANTALIS:
        return f"TANTALIS {item.crown_file_number}/{item.disposition_number}/{item.parcel_number}"
    return "Uploaded area of interest"


def build_ast_job(
    item: JobQueueItem,
    *,
    registry_dir: str | Path | None,
    oracle_connection: Optional[OracleConnection] = None,
) -> AstJob:
    """Turn one queue message into the AstJob the worker runs.

    The job keeps the id the API gave it, so the results are published under the
    same id the API hands back to the browser.
    """
    return AstJob(
        job_id=UUID(item.job_id),
        registries=load_registries(item.region, registry_dir, suppress_tab3=item.suppress_tab3),
        created_at=item.created_at,
        user=item.name,
        aoi_id=item.job_id,
        aoi_name=_aoi_name(item),
        aoi=resolve_aoi(item, oracle_connection),
        status=JobStatus.QUEUED,
        generate_maps=item.generate_maps,
        export_overlap_results=item.export_overlap_results,
        suppress_tab3=item.suppress_tab3,
        region=item.region,
        crown_file_number=item.crown_file_number,
        disposition_number=item.disposition_number,
        parcel_number=item.parcel_number,
        tab1_registry=TAB1_REGISTRY,
    )
