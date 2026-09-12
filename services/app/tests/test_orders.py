from fastapi.testclient import TestClient


def test_list_orders_returns_samples(client: TestClient) -> None:
    response = client.get("/api/orders")

    assert response.status_code == 200
    assert response.json() == [
        {"id": 1, "item": "widget", "quantity": 2},
        {"id": 2, "item": "gadget", "quantity": 1},
    ]


def test_create_order_returns_created_order(client: TestClient) -> None:
    response = client.post("/api/orders", json={"item": "sprocket", "quantity": 3})

    assert response.status_code == 201
    created = response.json()
    assert created == {"id": 3, "item": "sprocket", "quantity": 3}

    listed = client.get("/api/orders").json()
    assert len(listed) == 3
    assert created in listed


def test_create_order_rejects_invalid_body(client: TestClient) -> None:
    assert client.post("/api/orders", json={"item": "", "quantity": 1}).status_code == 422
    assert client.post("/api/orders", json={"item": "thing", "quantity": 0}).status_code == 422


def test_orders_unavailable_while_unhealthy(client: TestClient) -> None:
    client.post("/simulate/unhealthy_application")

    assert client.get("/api/orders").status_code == 503
    assert client.post("/api/orders", json={"item": "thing", "quantity": 1}).status_code == 503
