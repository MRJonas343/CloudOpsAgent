"""Typed response and request models for the simulated application."""

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    service: str


class MetricSnapshot(BaseModel):
    service: str
    status: str
    cpu_percent: float
    memory_percent: float
    request_count: int
    error_count: int
    error_rate: float
    latency_ms_p95: float
    requests_per_second: float


class OrderCreate(BaseModel):
    item: str = Field(min_length=1)
    quantity: int = Field(gt=0)


class Order(BaseModel):
    id: int
    item: str
    quantity: int


class SimulationRequest(BaseModel):
    duration_seconds: int | None = None


class SimulationStatus(BaseModel):
    enabled: bool
    mode: str | None
    started_at: float | None
    expires_at: float | None
    remaining_seconds: float | None
    duration_seconds: int | None
