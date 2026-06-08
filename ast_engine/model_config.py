from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # These will look for env vars: LOG_LEVEL, LOG_FILE
    log_level: str = "INFO"
    log_file: str | None = None
    
    # Optional: read from a .env file if it exists
    model_config = SettingsConfigDict(env_file=".env")

# Initialize globally
settings = Settings()