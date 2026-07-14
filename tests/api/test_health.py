from fastapi.testclient import TestClient

from api.main import app


def test_health_endpoint():
    response = TestClient(app).get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    # the 5.9.2 shape ships from day one; F10 fills the version
    assert "model_version" in response.json()
