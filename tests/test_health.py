from fastapi.testclient import TestClient

from learning_assistant.main import app


def test_health_endpoint() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"message": "Hello, world"}
