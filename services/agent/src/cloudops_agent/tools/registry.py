"""The execution boundary: registration, validation, timeout, and audit.

``ToolRegistry.invoke`` is deny-by-default. An unknown name raises
:class:`UnknownToolError` and nothing runs. A registered call:

1. validates its keyword arguments through the tool's ``input_model`` (if any),
2. runs inside the tool's declared ``timeout_seconds``,
3. emits one structured audit record with the tool name, risk, read-only flag, a
   redacted input summary, the outcome, and the duration in milliseconds.

Failures are logged and re-raised; a failed call is never reported as success.
"""

from __future__ import annotations

import concurrent.futures
import json
import logging
from time import perf_counter
from typing import Any

from pydantic import BaseModel

from cloudops_agent.tools.base import Tool, ToolSpec

_AUDIT_LOGGER = logging.getLogger("cloudops_agent.audit")
if not _AUDIT_LOGGER.handlers:
    _AUDIT_LOGGER.addHandler(logging.NullHandler())

_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=8, thread_name_prefix="cloudops-tool")

_REDACT_MARKERS = ("token", "secret", "password", "passwd", "credential", "authorization", "key")
_MAX_SUMMARY_LENGTH = 120


class ToolError(Exception):
    """Base class for errors raised at the tool boundary."""


class UnknownToolError(ToolError, LookupError):
    """Raised when invoking a tool name that was never registered."""

    def __init__(self, name: str) -> None:
        super().__init__(f"tool '{name}' is not registered")
        self.name = name


class ToolTimeoutError(ToolError, TimeoutError):
    """Raised when a tool exceeds its declared timeout."""

    def __init__(self, name: str, timeout_seconds: float) -> None:
        super().__init__(f"tool '{name}' exceeded its {timeout_seconds:g}s timeout")
        self.name = name
        self.timeout_seconds = timeout_seconds


def _redact(value: Any) -> Any:
    """Recursively redact secret-looking keys and truncate long strings."""
    if isinstance(value, dict):
        redacted: dict[Any, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(marker in lowered for marker in _REDACT_MARKERS):
                redacted[key] = "***"
            else:
                redacted[key] = _redact(item)
        return redacted
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    if isinstance(value, str) and len(value) > _MAX_SUMMARY_LENGTH:
        return value[: _MAX_SUMMARY_LENGTH - 3] + "..."
    return value


def _describe_input_model(model: type[BaseModel] | None) -> str:
    """Render a tool's expected parameters from its Pydantic input schema.

    Returns ``"none"`` when the tool takes no validated input, otherwise a
    comma-separated list of ``name: type (bounds)`` entries. ``?`` marks an
    optional parameter.
    """
    if model is None:
        return "none"
    schema = model.model_json_schema()
    properties: dict[str, Any] = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    parts: list[str] = []
    for name, prop in properties.items():
        type_name = str(prop.get("type", "value"))
        bounds: list[str] = []
        if "minimum" in prop:
            bounds.append(f"min {prop['minimum']}")
        if "maximum" in prop:
            bounds.append(f"max {prop['maximum']}")
        bound_text = f" ({', '.join(bounds)})" if bounds else ""
        optional = "" if name in required else "?"
        parts.append(f"{name}: {type_name}{bound_text}{optional}")
    return ", ".join(parts) if parts else "none"


class ToolRegistry:
    """Holds registered tools and is the only place a tool is executed."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register ``tool``; duplicate names are rejected."""
        name = tool.spec.name
        if name in self._tools:
            raise ValueError(f"tool '{name}' is already registered")
        self._tools[name] = tool

    def get(self, name: str) -> Tool:
        """Return the registered tool or raise :class:`UnknownToolError`."""
        tool = self._tools.get(name)
        if tool is None:
            raise UnknownToolError(name)
        return tool

    def names(self) -> list[str]:
        """Return the registered tool names in registration order."""
        return list(self._tools)

    def specs(self) -> list[ToolSpec]:
        """Return the registered tool specs in registration order."""
        return [tool.spec for tool in self._tools.values()]

    def describe(self) -> str:
        """Return a short text catalogue of registered tools for prompts."""
        lines = []
        for spec in self.specs():
            mode = "read-only" if spec.read_only else "mutating"
            lines.append(f"- {spec.name} [{mode}, risk {int(spec.risk_level)}]: {spec.description}")
        return "\n".join(lines)

    def remediation_catalogue(self) -> str:
        """Return the catalogue of mutating actions available for remediation.

        Only non-read-only tools are listed, because those are the only actions
        the executor will run. Each entry states the action name, what it does,
        its risk level, and the exact parameter names and bounds the executor
        validates, so the planner cannot propose an action or parameter that
        does not exist.
        """
        lines: list[str] = []
        for spec in self.specs():
            if spec.read_only:
                continue
            lines.append(f"- {spec.name} [risk {int(spec.risk_level)}]: {spec.description}")
            lines.append(f"  parameters: {_describe_input_model(spec.input_model)}")
        if not lines:
            return "(no remediation actions are registered)"
        return "\n".join(lines)

    def invoke(self, name: str, **kwargs: Any) -> Any:
        """Validate, run under timeout, and audit a single tool call.

        Unknown tools raise :class:`UnknownToolError` before anything runs.
        Invalid input, timeouts, and tool errors are logged and re-raised.
        """
        started = perf_counter()
        tool = self._tools.get(name)
        if tool is None:
            duration_ms = round((perf_counter() - started) * 1000, 3)
            self._audit(
                name=name,
                spec=None,
                inputs=_redact(kwargs),
                outcome="denied",
                duration_ms=duration_ms,
                error=f"unknown tool '{name}'",
            )
            raise UnknownToolError(name)

        spec = tool.spec
        inputs = _redact(kwargs)
        try:
            call_kwargs = self._validate(spec, kwargs)
        except Exception as exc:
            self._audit(
                name=name,
                spec=spec,
                inputs=inputs,
                outcome="invalid_input",
                duration_ms=round((perf_counter() - started) * 1000, 3),
                error=str(exc),
            )
            raise

        try:
            result = _run_with_timeout(tool, call_kwargs, spec.timeout_seconds)
        except concurrent.futures.TimeoutError as exc:
            self._audit(
                name=name,
                spec=spec,
                inputs=inputs,
                outcome="timeout",
                duration_ms=round((perf_counter() - started) * 1000, 3),
                error=f"exceeded {spec.timeout_seconds:g}s timeout",
            )
            raise ToolTimeoutError(name, spec.timeout_seconds) from exc
        except Exception as exc:
            self._audit(
                name=name,
                spec=spec,
                inputs=inputs,
                outcome="error",
                duration_ms=round((perf_counter() - started) * 1000, 3),
                error=str(exc),
            )
            raise

        self._audit(
            name=name,
            spec=spec,
            inputs=inputs,
            outcome="success",
            duration_ms=round((perf_counter() - started) * 1000, 3),
        )
        return result

    @staticmethod
    def _validate(spec: ToolSpec, kwargs: dict[str, Any]) -> dict[str, Any]:
        """Validate kwargs through ``input_model`` when the tool declares one."""
        if spec.input_model is None:
            return dict(kwargs)
        return spec.input_model.model_validate(kwargs).model_dump()

    @staticmethod
    def _audit(
        *,
        name: str,
        spec: ToolSpec | None,
        inputs: Any,
        outcome: str,
        duration_ms: float,
        error: str | None = None,
    ) -> None:
        """Emit one structured audit record for a tool call attempt."""
        record: dict[str, Any] = {
            "event": "tool_call",
            "tool": name,
            "risk": spec.risk_level.name if spec is not None else None,
            "risk_level": int(spec.risk_level) if spec is not None else None,
            "read_only": spec.read_only if spec is not None else None,
            "input": inputs,
            "outcome": outcome,
            "duration_ms": duration_ms,
        }
        if error is not None:
            record["error"] = error
        _AUDIT_LOGGER.info(json.dumps(record, default=str))


def _run_with_timeout(tool: Tool, kwargs: dict[str, Any], timeout_seconds: float) -> Any:
    """Run ``tool.run(**kwargs)`` in a worker thread under a hard time bound."""
    future = _EXECUTOR.submit(tool.run, **kwargs)
    return future.result(timeout=timeout_seconds)
