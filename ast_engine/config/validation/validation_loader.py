from pathlib import Path
import logging
import yaml
from yaml.constructor import ConstructorError
from ast_engine.config.paths import project_path
from ast_engine.core.validation.models import ValidationConfig
from ast_engine.core.validation.exceptions import ValidationConfigError
from ast_engine.core.validation.schema import ValidationProfile
from pydantic import ValidationError


logger = logging.getLogger(__name__)


def load_validation_config(
    config_path: str | Path | None,
    *,
    geometry_validation: bool,
    spatial_validation: bool,
    config_root: Path,
    profile: ValidationProfile | str = ValidationProfile.RUNTIME,
) -> ValidationConfig:
    """Bind a shared policy to the caller's profile and enabled components."""

    try:
        active_profile = ValidationProfile(profile)
    except ValueError as exc:
        raise ValidationConfigError(f"Unknown validation profile: {profile!r}.") from exc

    logger.debug(
        "Loading validation config from %s | geometry_validation=%s | spatial_validation=%s",
        config_path,
        geometry_validation,
        spatial_validation,
    )

    # Nothing enabled: no configuration file is required.
    if not geometry_validation and not spatial_validation:
        logger.debug(
            "Validation disabled | geometry_validation=%s | spatial_validation=%s",
            geometry_validation,
            spatial_validation,
        )
        return ValidationConfig(profile=active_profile, geometry=None, spatial=None)

    if config_path is None or not str(config_path).strip():
        raise ValidationConfigError(
            "A config path is required when validation is enabled."
        )

    path = project_path(config_path, root=config_root)

    if not path.is_absolute():
        root = Path(config_root).expanduser()

        if not root.is_absolute():
            raise ValidationConfigError("config_root must be an absolute path.")

        path = root / path
    logger.debug("Resolved validation config path: %s", path)

    try:
        with path.open(encoding="utf-8") as stream:
            document = yaml.load(stream, Loader=UniqueKeySafeLoader)

        if not isinstance(document, dict):
            raise ValidationConfigError(f"{path}: expected a YAML mapping.")

        if "profile" in document:
            raise ValidationConfigError(
                f"{path}: 'profile' is selected at startup; use 'run_in' on geometry "
                "rules or spatial layers in YAML."
            )

        logger.debug("YAML document loaded as: %s", document)

        config = ValidationConfig.model_validate({**document, "profile": active_profile})

        logger.debug(
            "ValidationConfig loaded from %s | geometry=%s | spatial=%s",
            path,
            "Yes" if config.geometry is not None else "No",
            "Yes" if config.spatial is not None else "No",
        )

    except (
        OSError,
        UnicodeError,
        yaml.YAMLError,
        ValidationError,
    ) as exc:
        raise ValidationConfigError(
            f"Could not load validation config {path}: {exc}"
        ) from exc

    if geometry_validation and config.geometry is None:
        raise ValidationConfigError(
            f"{path}: geometry validation is enabled, "
            "but the 'geometry' section is missing or null."
        )

    if spatial_validation and config.spatial is None:
        raise ValidationConfigError(
            f"{path}: spatial validation is enabled, "
            "but the 'spatial' section is missing or null."
        )

    # TODO: We will need to consider the pathing to the file datasets. Where they
    # live and how to resolve them. For now, we will just return the config as is.

    # Recursively converts nested configuration models into dictionaries.
    # Allows for re-validation of the complete configuration, after the
    # datasource paths have been expanded.
    data = config.model_dump(mode="python", round_trip=True)

    logger.debug(
        "ValidationConfig loaded to dictionary for path expansion."
    )

    if not geometry_validation:
        data["geometry"] = None

    if not spatial_validation:
        data["spatial"] = None

    for layer in data["spatial"] or ():
        if layer["data_adapter"] == "file":
            layer["datasource"] = str(project_path(layer["datasource"], root=config_root))

    logger.debug(
        "ValidationConfig datasource paths resolved for %s sources.",
        len(data["spatial"] or ()),
    )

    try:
        # Rebuilds and validates the complete configuration,
        # including nested geometry/spatial rules and model validators.
        return ValidationConfig.model_validate(data)


    except ValidationError as exc:
        raise ValidationConfigError(
            f"{path}: invalid configuration after data source resolution: {exc}"
        ) from exc


class UniqueKeySafeLoader(yaml.SafeLoader):
    """Reject duplicate keys within the same YAML mapping."""

    def construct_mapping(self, node, deep=False):
        mapping = super().construct_mapping(node, deep=deep)
        first_seen = {}

        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)

            if key in first_seen:
                raise ConstructorError(
                    f"first occurrence of {key!r}", first_seen[key],
                    f"duplicate YAML key {key!r}", key_node.start_mark,
                )

            first_seen[key] = key_node.start_mark

        return mapping