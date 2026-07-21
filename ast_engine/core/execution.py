'''
This code will orchestrate the pipeline from AOI --> results
'''
import logging
from ast_engine.config.logging_config import setup_logging
from ast_engine.utils.diagnostics import DiagnosticTracker

setup_logging()
logger = logging.getLogger(__name__)

def sample_logging(test_message: str):
    logger.debug("Sample logging started")
    diag = DiagnosticTracker()
    diag.log(test_message)
    logger.debug("Sample logging complete")

if __name__ == "__main__":
    logger.info("Starting execution")
    sample_logging("This is a sample message")
    logger.info("Execution Complete")
