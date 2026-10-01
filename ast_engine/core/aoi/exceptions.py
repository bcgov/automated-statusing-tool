class AOIError(Exception):
    """Base exception for AOI processing errors."""


class AOIBuildError(AOIError):
    """
    Raised when the AOI builder fails while orchestrating the build workflow.

    This exception is raised at the builder boundary and wraps the module-level
    exception that caused the build failure.
    """

    def __init__(
        self,
        message: str,
        *,
        stage: str | None = None,
        aoi_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.aoi_id = aoi_id


class SpatialDataError(AOIError):
    """Raised when spatial input data is missing, malformed, or unusable."""


class DataCRSError(SpatialDataError):
    """Raised when spatial data has a missing, invalid, or incompatible CRS."""


class SpatialGeometryError(SpatialDataError):
    """Raised when spatial geometry is missing, empty, invalid, or unsupported."""


class AOIRequestError(AOIError):
    """Raised when an AOI request is invalid."""


class AOINormalizationError(AOIError):
    """Raised when AOI normalization fails."""

class AOIInspectionError(AOIError):
    """Raised when AOI inspection fails."""


class AOIValidationError(AOIError):
    """Raised when AOI validation rules fail."""


class AOIPartBuildError(AOIError):
    """Raised when the AOI part builder cannot produce an AOI part."""


def root_cause(exc: BaseException) -> BaseException:
    current = exc

    while current.__cause__ is not None:
        current = current.__cause__

    return current