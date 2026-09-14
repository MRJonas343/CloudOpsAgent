"""Public surface of the registered tool layer.

The registry is deny-by-default: only tools registered here can run, and an
unknown tool name never executes. The default registry holds the read-only app
tools (Risk 0) plus the guarded mutating tool ``scale_service`` (Risk 2), whose
parameters are validated at the boundary before it runs.
"""

from __future__ import annotations

from functools import lru_cache

from cloudops_agent.config import Settings
from cloudops_agent.tools.app_tools import build_app_tools
from cloudops_agent.tools.base import Tool, ToolSpec
from cloudops_agent.tools.registry import (
    ToolError,
    ToolRegistry,
    ToolTimeoutError,
    UnknownToolError,
)
from cloudops_agent.tools.remediation_tools import build_remediation_tools

__all__ = [
    "Tool",
    "ToolError",
    "ToolRegistry",
    "ToolSpec",
    "ToolTimeoutError",
    "UnknownToolError",
    "build_app_tools",
    "build_remediation_tools",
    "get_tool_registry",
]


def get_tool_registry(settings: Settings | None = None) -> ToolRegistry:
    """Return the cached default registry of read-only and mutating app tools.

    Caching is keyed by the two settings that shape the tools (base URL and
    request timeout), so repeated calls with the same configuration reuse one
    registry.
    """
    effective = settings or Settings()
    return _build_registry(effective.app_base_url, effective.app_request_timeout_seconds)


@lru_cache(maxsize=8)
def _build_registry(base_url: str, timeout_seconds: float) -> ToolRegistry:
    """Build and cache a registry for one (base URL, timeout) pair."""
    tool_settings = Settings(
        app_base_url=base_url,
        app_request_timeout_seconds=timeout_seconds,
    )
    registry = ToolRegistry()
    for tool in build_app_tools(tool_settings):
        registry.register(tool)
    for tool in build_remediation_tools(tool_settings):
        registry.register(tool)
    return registry
