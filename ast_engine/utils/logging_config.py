# ast_engine/utils/logging_config.py
import logging.config
import sys
from ast_engine.model_config import settings

def setup_logging():
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
                "level": settings.log_level.upper(),
            },
        },
        "root": {
            "handlers": ["console"],
            "level": settings.log_level.upper(),
        },
    }

    if settings.log_file:
        config["handlers"]["file"] = {
            "class": "logging.FileHandler",
            "filename": settings.log_file,
            "formatter": "standard",
            "level": settings.log_level.upper(),
            "encoding": "utf-8",
        }
        config["root"]["handlers"].append("file")

    logging.config.dictConfig(config)