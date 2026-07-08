from ast_engine.config.settings import Settings
from ast_engine.config.logging import setup_logging

def bootstrap():
    """Initialize app on startup: validate config, setup logging, etc."""
    # Setup logging first
    logger = setup_logging()
    
    # Validate system requirements
    issues = Settings.validate_system()
    if issues:
        logger.error(f"System validation failed: {issues}")
        raise RuntimeError(f"Configuration validation failed: {issues}")
    
    logger.info(f"App initialized in {Settings.environment} mode")
    return logger

__initialized = False

def ensure_initialized():
    """Idempotent initialization check."""
    global __initialized
    if not __initialized:
        bootstrap()
        __initialized = True6