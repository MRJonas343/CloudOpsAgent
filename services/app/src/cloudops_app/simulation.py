"""Bounded, deterministic fault simulation for the simulated application.

The controller owns a single active fault at a time. Durations are clamped to
``[1, max_duration_seconds]`` and the fault auto-expires once the injected clock
passes ``expires_at`` (no background threads, no sleeping).
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

MIN_DURATION_SECONDS = 1


class FaultMode(str, Enum):
    """Fault modes understood by the MVP simulation mechanism."""

    unhealthy_application = "unhealthy_application"
    traffic_spike = "traffic_spike"


@dataclass
class SimulationState:
    """Immutable-ish snapshot of the currently active fault, if any."""

    mode: FaultMode | None = None
    started_at: float | None = None
    expires_at: float | None = None
    duration_seconds: int | None = None


class SimulationController:
    """Owns the active fault and enforces the duration bound."""

    def __init__(
        self,
        *,
        max_duration_seconds: int,
        default_duration_seconds: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max_duration_seconds = max_duration_seconds
        self._default_duration_seconds = default_duration_seconds
        self._clock = clock
        self._state = SimulationState()

    def activate(self, mode: FaultMode, duration_seconds: int | None = None) -> SimulationState:
        """Activate ``mode`` for a clamped duration and return the new state."""
        requested = self._default_duration_seconds if duration_seconds is None else duration_seconds
        duration = max(MIN_DURATION_SECONDS, min(requested, self._max_duration_seconds))
        now = self._clock()
        self._state = SimulationState(
            mode=mode,
            started_at=now,
            expires_at=now + duration,
            duration_seconds=duration,
        )
        return self._state

    def reset(self) -> None:
        """Clear any active fault."""
        self._state = SimulationState()

    def current(self) -> SimulationState:
        """Return the active state, auto-expiring it when the clock has passed."""
        if (
            self._state.mode is not None
            and self._state.expires_at is not None
            and self._clock() >= self._state.expires_at
        ):
            self._state = SimulationState()
        return self._state

    def active_mode(self) -> FaultMode | None:
        """Return the active fault mode, or ``None`` when none is active."""
        return self.current().mode

    def remaining_seconds(self) -> float | None:
        """Seconds until the active fault expires, or ``None`` when inactive."""
        state = self.current()
        if state.expires_at is None:
            return None
        return max(0, round(state.expires_at - self._clock()))


def parse_mode(value: str) -> FaultMode | None:
    """Parse a user-supplied mode string, returning ``None`` when unknown."""
    try:
        return FaultMode(value)
    except ValueError:
        return None
