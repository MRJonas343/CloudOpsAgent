"""AWS Bedrock model connection for the agent workflow.

Builds a ``ChatBedrockConverse`` client for Claude Sonnet 4.5 and exposes a
minimal ``create_agent`` graph used as a one-shot connectivity check:

    uv run --directory services/agent python -m cloudops_agent.graph.model.connection

The incident workflow builds its own graph in ``cloudops_agent.graph.build`` on
top of ``get_model()``.

Claude Sonnet 4.5 is only served through cross-region inference profiles on
Bedrock, so the model id keeps the ``us.`` prefix. Use ``global.`` for worldwide
routing or ``eu.``/``jp.`` for a different geography.
"""

from __future__ import annotations

from langchain.agents import create_agent
from langchain_aws import ChatBedrockConverse

from cloudops_agent.config import Settings

DEFAULT_SYSTEM_PROMPT = "You are a concise cloud operations assistant."


def get_model(settings: Settings | None = None) -> ChatBedrockConverse:
    """Build the Bedrock chat model from settings.

    ``bedrock_api_key`` is passed explicitly so a Bedrock API key (bearer token)
    works even when boto3 would otherwise look for IAM credentials. When it is
    unset, boto3 falls back to its normal credential chain.
    """
    resolved = settings or Settings()
    return ChatBedrockConverse(
        model=resolved.bedrock_model_id,
        region_name=resolved.aws_region,
        temperature=0,
        bedrock_api_key=resolved.aws_bearer_token_bedrock,
    )


def get_agent(settings: Settings | None = None):
    """Build the minimal agent graph used to verify connectivity.

    This is intentionally tool-less; the deterministic incident workflow and its
    registered tools arrive in later phases.
    """
    return create_agent(
        model=get_model(settings),
        tools=[],
        system_prompt=DEFAULT_SYSTEM_PROMPT,
    )


def main() -> None:
    """Invoke a minimal agent once to verify the Bedrock connection."""
    graph = get_agent()
    result = graph.invoke(
        {"messages": [{"role": "user", "content": "Reply with exactly: connection ok"}]}
    )
    print(result["messages"][-1].content_blocks)


if __name__ == "__main__":
    main()
