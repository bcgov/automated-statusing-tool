
# Add adapter exceptions here

class DataAdapterError(Exception):
    """Base exception for data adapter layer."""


class DataReadError(DataAdapterError):
    """Raised when a data source cannot be read."""

class DataCrsError(DataAdapterError):
    """Raised when there is a issue with transforming data source Crs"""