import logging.config
import sys
from ast_engine.config.settings import Settings

def setup_logging():
    """Configure logging based on settings."""
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
                "level": Settings.log_level,
            },
        },
        "root": {
            "handlers": ["console"],
            "level": Settings.log_level,
        },
    }
    
    if Settings.log_file:
        config["handlers"]["file"] = {
            "class": "logging.FileHandler",
            "filename": Settings.log_file,
            "formatter": "standard",
            "level": Settings.log_level,
        }
        config["root"]["handlers"].append("file")
    
    logging.config.dictConfig(config)
    return logging.getLogger(__name__)