"""Shared API/Redis AOI construction. Call once per process at startup."""

from contextlib import ExitStack
from collections.abc import Mapping
import logging


from ast_engine.config.paths import PROJECT_ROOT
from ast_engine.config.settings import Settings
from ast_engine.core.aoi import AOIBuilder
from ast_engine.core.aoi.validator import AOIValidator
from ast_engine.core.data_adapters.oracle.connection import OracleConnection
from ast_engine.core.data_adapters.base import BaseSpatialAdapter
from ast_engine.core.validation.schema import ValidationProfile
from ast_engine.core.validation.geometry.geometry_validation import GeometryValidator
from ast_engine.core.validation.spatial.spatial_validation import SpatialValidator
from ast_engine.core.validation.spatial.reference_loader import load_reference_layers

from .validation_loader import load_validation_config

logger = logging.getLogger(__name__)

def create_aoi_builder(
    settings: Settings,
    *,
    profile: ValidationProfile,
    connection: OracleConnection | None = None,
    adapters: Mapping[str, BaseSpatialAdapter] | None = None,
) -> AOIBuilder:
    """Build AOI validation, borrowing a job connection when supplied."""

    logger.debug(
        "Loading AOI validation config from %s for profile %s",
        settings.aoi_validation_config_path,
        profile,
    )

    config = load_validation_config(
        settings.aoi_validation_config_path,
        geometry_validation=settings.validate_aoi_geometry,
        spatial_validation=settings.validate_aoi_spatial,
        config_root=PROJECT_ROOT,
    )
    logger.debug("ValidationConfig established for profile %s "
                 "Geometry Vaidation: %s, Spatial Validation: %s",
                 profile,
                 "Yes" if config.geometry is not None else "No",
                 "Yes" if config.spatial is not None else "No"
    )

    # Preserve supplied adapters without modifying the caller's mapping.
    resolved_adapters = dict(adapters) if adapters is not None else {}
    required_kinds = {
        layer.data_adapter for layer in config.spatial or ()
    }

    with ExitStack() as resources:
        if "file" in required_kinds and "file" not in resolved_adapters:
            from ast_engine.core.data_adapters.file import FileSpatialAdapter

            resolved_adapters["file"] = FileSpatialAdapter()

        if "oracle" in required_kinds and "oracle" not in resolved_adapters:
            from ast_engine.core.data_adapters.oracle import OracleAdapter

            oracle_session = connection

            if oracle_session is None:
                if not all(
                    (
                        settings.oracle_user,
                        settings.oracle_password,
                        settings.oracle_host,
                        settings.oracle_database,
                    )
                ):
                    raise ValueError(
                        "Oracle settings are required when no connection "
                        "or Oracle adapter is supplied."
                    )

                oracle_session = OracleConnection(
                    username=settings.oracle_user,
                    password=settings.oracle_password.get_secret_value(),
                    hostname=(
                        f"{settings.oracle_host}:{settings.oracle_port}/"
                        f"{settings.oracle_database}"
                    ),
                )

                # Register cleanup only for a session created here.
                resources.enter_context(oracle_session)

            if (
                oracle_session.connection is None
                or oracle_session.cursor is None
            ):
                raise ValueError(
                    "Oracle validation requires an open connection and cursor."
                )

            resolved_adapters["oracle"] = OracleAdapter(
                connection=oracle_session.connection,
                cursor=oracle_session.cursor,
            )
        logger.debug(
                    "Adapters resolved "
                    "File: %s, Oracle: %s",
                    "Yes" if "file" in resolved_adapters else "No",
                    "Yes" if "oracle" in resolved_adapters else "No",
        )

        references = load_reference_layers(
            config.spatial,
            adapters=resolved_adapters,
            target_crs=settings.system_crs,
        )
        logger.debug(
            "Reference sources loaded: %s",
            list(references),
        )

        geometry_validator = (
            GeometryValidator(config.geometry)
            if config.geometry is not None
            else None
        )
        logger.debug("Geometry validator established: %s", "Yes" if geometry_validator else "No")

        spatial_validator = (
            SpatialValidator(
                config.spatial,
                reference_layers=references,
                target_crs=settings.system_crs,
                profile=profile,
            )
            if config.spatial is not None
            else None
        )
        logger.debug("Spatial validator established: %s", "Yes" if spatial_validator else "No")

        return AOIBuilder(
            validator=AOIValidator(
                geometry_validator=geometry_validator,
                spatial_validator=spatial_validator,
                profile=profile,
            )
        )
