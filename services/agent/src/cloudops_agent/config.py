"""Agent settings loaded from the environment."""

from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_env_file() -> Path | None:
    """Return the nearest ``.env`` found walking up from this module.

    In local development this resolves to the repository root ``.env``; in the
    container no ``.env`` exists (configuration arrives via environment
    variables), so the search returns ``None``.
    """
    for parent in Path(__file__).resolve().parents:
        candidate = parent / ".env"
        if candidate.is_file():
            return candidate
    return None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AGENT_",
        env_file=_find_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    service_port: int = 8000
    log_level: str = "INFO"
    app_base_url: str = "http://app:8001"
    poll_interval_seconds: int = 10

    # LLM provider. The client lives in cloudops_agent.graph.model.connection so
    # the provider can be swapped without touching the workflow.
    llm_provider: str = "aws-bedrock"
    bedrock_model_id: str = Field(
        default="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
        validation_alias=AliasChoices("AGENT_BEDROCK_MODEL_ID", "BEDROCK_MODEL_ID"),
    )
    aws_region: str = Field(
        default="us-east-1",
        validation_alias=AliasChoices("AWS_REGION", "AGENT_AWS_REGION"),
    )
    aws_bearer_token_bedrock: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "AWS_BEARER_TOKEN_BEDROCK",
            "AGENT_AWS_BEARER_TOKEN_BEDROCK",
        ),
    )

    # Monitoring module (internal to the agent).
    monitoring_enabled: bool = True
    traffic_spike_rps_threshold: float = 20.0
    app_request_timeout_seconds: float = 5.0


settings = Settings()
