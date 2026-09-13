"""Helpers for reading typed configuration files.

Keeping the file reading here means modules such as ``cloudops_agent.graph.agents``
declare *what* they need instead of *how* it is parsed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class ConfigFile:
    """Lazily read and cache a YAML configuration file."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._data: dict[str, Any] | None = None

    @property
    def path(self) -> Path:
        """Location of the configuration file."""
        return self._path

    def load(self) -> dict[str, Any]:
        """Return the parsed mapping, reading the file only once."""
        if self._data is None:
            self._data = self._read()
        return self._data

    def reload(self) -> dict[str, Any]:
        """Drop the cache and read the file again (handy while editing prompts)."""
        self._data = None
        return self.load()

    def _read(self) -> dict[str, Any]:
        if not self._path.is_file():
            raise FileNotFoundError(f"configuration file not found: {self._path}")
        with self._path.open(encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
        if not isinstance(data, dict):
            raise ValueError(f"configuration file must contain a mapping: {self._path}")
        return data
