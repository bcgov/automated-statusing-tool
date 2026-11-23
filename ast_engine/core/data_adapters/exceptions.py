
# Add adapter exceptions here

class DataAdapterError(Exception):
    """Base exception for data adapter layer."""

class DataReadError(DataAdapterError):
    """Raised when a data source cannot be read."""

class DataConnectionError(DataAdapterError):
    """Raised when the database connection is lost: no other dataset can be read on it."""

class DataCrsError(DataAdapterError):
    """Raised when there is a issue with transforming data source Crs"""

class AdapterConfigurationError(DataAdapterError):
    """Adapter configuration conflicts with dataset metadata."""