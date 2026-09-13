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
    replicas: int


class LogEntryModel(BaseModel):
    timestamp: str
    level: str
    service: str
    message: str
    path: str | None = None
    method: str | None = None
    status: int | None = None
    duration_ms: float | None = None


class LogListResponse(BaseModel):
    service: str
    count: int
    limit: int
    entries: list[LogEntryModel]


class ScaleRequest(BaseModel):
    replicas: int


class ScaleState(BaseModel):
    service: str
    replicas: int
    baseline_replicas: int
    min_replicas: int
    max_replicas: int


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
