"""Agent settings loaded from the environment."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGENT_", extra="ignore")

    service_port: int = 8000
    log_level: str = "INFO"
    app_base_url: str = "http://app:8001"
    poll_interval_seconds: int = 10
    llm_provider: str = "azure_foundry"


settings = Settings()
