class AOIValidationError(Exception):
    """Raised when the AOI fails validation."""

class AOINormalizationError(Exception):
    """Raised when the AOI fails normalization."""

class DataCRSError(Exception):
    """Raised when GDF has a missing or problematic CRS."""

class AOIGeometryError(Exception):
    """Raised when the AOI had Null or invalid geometry."""

class AOIGeometryTypeError(Exception):
    """Raised when the AOI has geometry of an unexpected type."""