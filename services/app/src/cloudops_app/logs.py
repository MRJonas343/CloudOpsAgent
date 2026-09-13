"""Bounded, in-memory, thread-safe log store for the simulated application.

The store keeps the most recent entries in a bounded ``deque`` behind a lock so
the agent's read-only tools can consult them over HTTP. Every entry is also
mirrored into the structured stdout logger so container logs stay useful.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone

SERVICE_NAME = "app"

VALID_LEVELS = ("info", "warning", "error")

_LEVEL_TO_LOGGING = {
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class LogEntry:
    """A single consultable log record."""

    timestamp: str
    level: str
    service: str
    message: str
    path: str | None = None
    method: str | None = None
    status: int | None = None
    duration_ms: float | None = None


class LogStore:
    """Bounded, thread-safe, in-memory log store.

    ``record`` appends and mirrors to stdout; ``recent`` and ``errors`` return
    snapshots newest-first; ``clear`` empties the store.
    """

    def __init__(self, max_entries: int = 500, *, service: str = SERVICE_NAME) -> None:
        self._max_entries = max(1, int(max_entries))
        self._service = service
        self._entries: deque[LogEntry] = deque(maxlen=self._max_entries)
        self._lock = threading.Lock()
        self._logger = logging.getLogger("cloudops_app.logs")

    @property
    def max_entries(self) -> int:
        """The configured upper bound on stored entries."""
        return self._max_entries

    @property
    def service(self) -> str:
        """The service name stamped on every entry."""
        return self._service

    def record(
        self,
        level: str,
        message: str,
        *,
        path: str | None = None,
        method: str | None = None,
        status: int | None = None,
        duration_ms: float | None = None,
    ) -> LogEntry:
        """Append an entry (normalizing unknown levels to ``info``) and mirror it."""
        normalized = level.lower()
        if normalized not in VALID_LEVELS:
            normalized = "info"
        entry = LogEntry(
            timestamp=_now_iso(),
            level=normalized,
            service=self._service,
            message=message,
            path=path,
            method=method,
            status=status,
            duration_ms=duration_ms,
        )
        with self._lock:
            self._entries.append(entry)
        self._mirror(entry)
        return entry

    def recent(self, limit: int | None = None) -> list[LogEntry]:
        """Return up to ``limit`` entries, newest first."""
        with self._lock:
            snapshot = list(self._entries)
        if limit is not None:
            snapshot = snapshot[-limit:] if limit > 0 else []
        snapshot.reverse()
        return snapshot

    def errors(self, limit: int | None = None) -> list[LogEntry]:
        """Return up to ``limit`` error-level entries, newest first."""
        with self._lock:
            snapshot = [entry for entry in self._entries if entry.level == "error"]
        if limit is not None:
            snapshot = snapshot[-limit:] if limit > 0 else []
        snapshot.reverse()
        return snapshot

    def clear(self) -> None:
        """Remove every stored entry."""
        with self._lock:
            self._entries.clear()

    def count(self) -> int:
        """Return the number of stored entries."""
        with self._lock:
            return len(self._entries)

    def _mirror(self, entry: LogEntry) -> None:
        self._logger.log(_LEVEL_TO_LOGGING.get(entry.level, logging.INFO), "%s", entry.message)
