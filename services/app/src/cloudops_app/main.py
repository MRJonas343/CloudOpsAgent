"""Minimal FastAPI entrypoint for the simulated application service."""

from fastapi import FastAPI

app = FastAPI(title="CloudOpsAgent Simulated Application", version="0.1.0")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "app"}
