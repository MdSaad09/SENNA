from fastapi.testclient import TestClient

from api.main import app


def test_health_endpoint():
    # a liveness probe with no lifespan run: no Postgres, no Redis, no manifest loaded.
    # It must still answer 200 with the 5.9.2 shape — the route reads app.state
    # defensively, so model_version is null here and a real version once startup fills it
    # (a bare attribute read would 500, which is what this test guards against).
    response = TestClient(app).get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    # the 5.9.2 shape ships from day one; F10 fills the version at startup
    assert "model_version" in response.json()
