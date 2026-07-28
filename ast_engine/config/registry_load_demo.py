import getpass
import os
import sys
from pathlib import Path

import logging

from ast_engine.config.logging_config import setup_logging
from ast_engine.config.registry import utils, models

setup_logging()
logger = logging.getLogger(__name__)

registry = utils.load_yaml("ast_engine/tests/registry/Test_Registry.yaml")
print(registry)

