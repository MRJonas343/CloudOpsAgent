"""Application settings loaded from the environment."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_", extra="ignore")

    service_port: int = 8001
    log_level: str = "INFO"
    simulation_enabled: bool = True
    simulation_max_duration_seconds: int = 300
    simulation_default_duration_seconds: int = 30


settings = Settings()
