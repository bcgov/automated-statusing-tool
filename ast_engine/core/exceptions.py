class SpatialDataError(Exception):
    """Spatial input is missing, malformed, or unusable."""


class DataCRSError(SpatialDataError):
    """Spatial data has a missing, invalid, or incompatible CRS."""


class SpatialGeometryError(SpatialDataError):
    """Spatial geometry is missing, empty, invalid, or unsupported."""