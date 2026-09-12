"""Shared fixtures for the simulated application test suite."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from cloudops_app.config import Settings
from cloudops_app.main import create_app


class FakeClock:
    """Controllable monotonic clock so expiry tests never sleep."""

    def __init__(self, start: float = 1000.0) -> None:
        self.value = start

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def settings() -> Settings:
    return Settings(
        simulation_enabled=True,
        simulation_max_duration_seconds=300,
        simulation_default_duration_seconds=30,
    )


@pytest.fixture
def client(settings: Settings, clock: FakeClock) -> Iterator[TestClient]:
    """A fresh app per test, ensuring simulation state and counters are reset."""
    with TestClient(create_app(settings=settings, clock=clock)) as test_client:
        yield test_client


@pytest.fixture
def disabled_client(clock: FakeClock) -> Iterator[TestClient]:
    disabled = Settings(
        simulation_enabled=False,
        simulation_max_duration_seconds=300,
        simulation_default_duration_seconds=30,
    )
    with TestClient(create_app(settings=disabled, clock=clock)) as test_client:
        yield test_client
