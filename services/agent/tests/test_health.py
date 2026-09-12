from fastapi.testclient import TestClient

from cloudops_agent.config import Settings
from cloudops_agent.main import create_app
from cloudops_agent.services.incident_store import IncidentStore

app = create_app(Settings(monitoring_enabled=False))
client = TestClient(app)


class StubClient:
    """Minimal stand-in for AppClient that never touches the network."""

    async def aclose(self) -> None:
        return None


def test_health_returns_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "agent"}


def test_create_app_accepts_injected_client_and_store() -> None:
    store = IncidentStore()
    application = create_app(
        Settings(monitoring_enabled=False),
        client=StubClient(),  # type: ignore[arg-type]
        store=store,
    )

    with TestClient(application) as test_client:
        assert test_client.get("/health").status_code == 200

    assert store.list() == []
