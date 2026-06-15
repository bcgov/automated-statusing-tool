from abc import ABC, abstractmethod
from dataclasses import dataclass
import geopandas as gpd
from .exceptions import DataCrsError

from typing import Iterable


# the spatial relationships a SpatialFilter can describe
_SPATIAL_PREDICATES = ("intersects", "within_distance", "touches", "nearest")


class SpatialFilter:
    """How to narrow a dataset down to an AOI before reading.

    One SpatialFilter describes the spatial filter for every adapter. Each
    adapter pushes it down its own way - the Oracle adapter into an SDO query,
    file adapters into a gpd.read_file bbox.

    aoi:       the area of interest, a GeoDataFrame.
    predicate: the spatial relationship to push down -
               'intersects' (default), 'within_distance', 'touches', 'nearest'.
    distance:  search distance in metres - required for 'within_distance'.
    k:         number of features to return - required for 'nearest'.
    """

    def __init__(
        self,
        *,
        aoi: gpd.GeoDataFrame,
        predicate: str = "intersects",
        distance: float | None = None,
        k: int | None = None,
    ):
        if aoi is None or aoi.empty:
            raise ValueError("SpatialFilter needs a non-empty AOI")
        if aoi.crs is None:
            raise ValueError("SpatialFilter AOI has no CRS defined")
        if predicate not in _SPATIAL_PREDICATES:
            raise ValueError(
                f"Unknown predicate {predicate!r}; expected one of "
                f"{', '.join(_SPATIAL_PREDICATES)}"
            )
        if predicate == "within_distance" and (distance is None or distance <= 0):
            raise ValueError(
                "predicate 'within_distance' needs a positive `distance` in metres"
            )
        if predicate == "nearest" and (
            k is None or not isinstance(k, int) or k <= 0
        ):
            raise ValueError(
                "predicate 'nearest' needs a positive whole-number `k`"
            )

        self.aoi = aoi
        self.predicate = predicate
        self.distance = distance
        self.k = k


class ReadOptions:
    """
    Optional read controls applicable to all spatial adapters.

    Adapters should push these down to the source (preferred)
    or apply them post-read if needed.
    """

    def __init__(
        self,
        *,
        spatial_filter: SpatialFilter | None = None,
        definition_query: str | None = None,
        keep_columns: Iterable[str] | None = None,
    ):
        # spatial_filter pushes an AOI filter down to the source.
        self.spatial_filter = spatial_filter
        self.definition_query = definition_query
        self.keep_columns = list(keep_columns) if keep_columns else None


@dataclass(frozen=True)
class DatasetInfo:
    """A dataset's metadata, read without loading all of its features.

    Filled in by an adapter's describe() and used at build time by the
    registry to record what each dataset looks like.

    geom_column:   name of the geometry column.
    crs:           coordinate reference system as an EPSG string, e.g. "EPSG:3005".
    geometry_type: "point", "line" or "polygon" - multipart geometries are
                   collapsed to their single-part name.
    columns:       the attribute (non-geometry) column names.
    row_count:     number of features, or None when the source cannot report it.
    """

    geom_column: str
    crs: str
    geometry_type: str
    columns: list[str]
    row_count: int | None


class BaseSpatialAdapter(ABC):
    """
    Source-agnostic base class for spatial adapters.
    """

    def read(
        self,
        *,
        read_options: ReadOptions | None = None,
        target_crs: str | None = None,
        **source_kwargs,
    ) -> gpd.GeoDataFrame:
        read_options = read_options or ReadOptions()

        gdf = self._read_impl(
            read_options=read_options,
            **source_kwargs,
        )

        self._validate_crs(gdf)

        if target_crs:
            gdf = self._reproject(gdf, target_crs)

        # Fallback filters (only applied if adapter didn't push down)
        gdf = self._apply_post_filters(gdf, read_options)

        return gdf

    @abstractmethod
    def _read_impl(
        self,
        *,
        read_options: ReadOptions,
        **source_kwargs,
    ) -> gpd.GeoDataFrame:
        """Adapter-specific read implementation"""

    @abstractmethod
    def describe(self, **source_kwargs) -> DatasetInfo:
        """Return a dataset's metadata without reading all of its features.

        Used at build time by the registry to record geometry type, CRS,
        columns and feature count per dataset. Each adapter reads this from
        its own source - the Oracle adapter from SDO metadata, the file
        adapter from the file's layer information.
        """

    # -----------------------------
    # Shared fallback behavior
    # -----------------------------

    def _apply_post_filters(
        self,
        gdf: gpd.GeoDataFrame,
        opts: ReadOptions,
    ) -> gpd.GeoDataFrame:
        # Adapters that pushed these down clear them first (see consume-and-clear
        # in OracleAdapter and FileSpatialAdapter). What is left here is the
        # fallback for fields the adapter could not handle at the source - the
        # file adapter relies on this for definition_query and keep_columns.
        if opts.definition_query:
            gdf = gdf.query(opts.definition_query)

        if opts.keep_columns:
            gdf = self._select_columns(gdf, opts.keep_columns)

        return gdf

    def _select_columns(
        self,
        gdf: gpd.GeoDataFrame,
        keep: list[str],
    ) -> gpd.GeoDataFrame:
        cols = set(keep) | {gdf.geometry.name}
        return gdf[[c for c in gdf.columns if c in cols]]

    def _validate_crs(self, gdf: gpd.GeoDataFrame) -> None:
        if gdf.crs is None:
            raise DataCrsError("Input dataset has no CRS defined")

    def _reproject(self, gdf, target_crs):
        try:
            return gdf.to_crs(target_crs)
        except Exception as exc:
            raise DataCrsError from exc
