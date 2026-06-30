class AOIError(Exception):
    """Base exception for AOI processing errors."""


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


class AOIBuildError(AOIError):
    """Raised when the AOI builder cannot produce an AOI."""


class AOIPartBuildError(AOIError):
    """Raised when the AOI part builder cannot produce an AOI part."""


def root_cause(exc: BaseException) -> BaseException:
    current = exc

    while current.__cause__ is not None:
        current = current.__cause__

    return current