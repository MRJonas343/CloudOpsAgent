"""Minimal FastAPI entrypoint for the agent service."""

from fastapi import FastAPI

app = FastAPI(title="CloudOpsAgent Agent", version="0.1.0")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "agent"}
