import logging.config
import sys
from ast_engine.config.settings import Settings

def setup_logging():
    """
    This function creates and applies a logging configuration based on values defined in `Settings`, including:
    - Log level
    - Log message formatting
    - Console output
    - Optional file logging

    Returns:
    - logging.Logger: A configured logger instance for the current module.

    Side Effects:
    - Configures the root logger.
    - May create and write to a log file if `settings.log_file` is specified.
    - Updates the global logging configuration for the current process.

    Usage:
    - Call `setup_logging()` during application startup before creating or using loggers elsewhere in the application..
    """

    settings = Settings()
    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": "%(asctime)s | %(name)s | %(levelname)s | %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "stream": sys.stdout,
                "formatter": "standard",
                "level": settings.log_level,
            },
        },
        "root": {
            "handlers": ["console"],
            "level": settings.log_level,
        },
    }
    
    if settings.log_file:
        config["handlers"]["file"] = {
            "class": "logging.FileHandler",
            "filename": settings.log_file,
            "formatter": "standard",
            "level": settings.log_level,
        }
        config["root"]["handlers"].append("file")
    
    logging.config.dictConfig(config)
    return logging.getLogger(__name__)
