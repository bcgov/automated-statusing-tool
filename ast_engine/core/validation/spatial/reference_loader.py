"""Load full reference datasets once at startup, before selecting a profile."""

from collections.abc import Mapping, Sequence
from types import MappingProxyType
import geopandas as gpd

from ast_engine.core.data_adapters.base import BaseSpatialAdapter, ReadOptions
from .spatial_validation import SpatialValidationError
from .models import SpatialLayerReferenceConfig

ReferenceKey = tuple[str, str]
ReferenceLayers = Mapping[ReferenceKey, gpd.GeoDataFrame]


def load_reference_layers(
    spatial: Sequence[SpatialLayerReferenceConfig] | None,
    *,
    adapters: Mapping[str, BaseSpatialAdapter],
    target_crs: str,
) -> ReferenceLayers:
    sources: dict[ReferenceKey, set[str]] = {}

    for layer in spatial or ():
        key = (layer.data_adapter, layer.datasource)
        fields = sources.setdefault(key, set())

        if layer.id_field is not None:
            fields.add(layer.id_field)

    cache = {}
    for (kind, datasource), fields in sources.items():
        if kind not in adapters:
            raise SpatialValidationError(f"No startup adapter supplied for {kind!r}.")
        try:
            options = ReadOptions(keep_columns=sorted(fields) or None)
            kwargs = (
                {"table": datasource}
                if kind == "oracle"
                else {"path": datasource}
            )
            # Crucial: no AOI spatial filter. Cache the whole configured source.
            cache[(kind, datasource)] = adapters[kind].read(
                read_options=options,
                target_crs=target_crs,
                **kwargs,
            )
        except Exception as exc:
            raise SpatialValidationError(
                f"Could not cache reference {datasource!r}: {exc}"
            ) from exc
    # The mapping is read-only; consumers must also treat its frames as read-only.
    return MappingProxyType(cache)
