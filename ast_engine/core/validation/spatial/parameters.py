from collections.abc import Mapping, Sequence

from ..schema import ValidationProfile
from ..common import checked_unit_ids
from ..spatial.models import SpatialLayerReferenceConfig


def resolve_expected_ids(
    layers: Sequence[SpatialLayerReferenceConfig] | None,
    parameters: Mapping[str, Sequence[str | int]] | None = None,
    *,
    profile: ValidationProfile = ValidationProfile.RUNTIME,
) -> dict[str, tuple[str | int, ...]]:
    """Bind this call's selections without mutating the shared policy.

    Keys from other configured profiles are accepted, but only active layers
    require selections. Entirely unknown parameter names are rejected.
    """
    layers = tuple(layers or ())
    supplied = dict(parameters or {})
    known_keys = {layer.expected_from for layer in layers if layer.expected_from}
    unknown = supplied.keys() - known_keys
    if unknown:
        raise ValueError(f"Unknown validation parameters: {sorted(unknown)!r}.")
    supplied = {key: checked_unit_ids(values) for key, values in supplied.items()}
    resolved = {}
    for layer in layers:
        if profile not in layer.run_in:
            continue
        values = layer.expected_ids
        if layer.expected_from:
            if not supplied.get(layer.expected_from):
                raise ValueError(
                    f"Layer {layer.name!r} requires nonempty parameter {layer.expected_from!r}."
                )
            values = supplied[layer.expected_from]
        resolved[layer.name] = tuple(values)
    return resolved