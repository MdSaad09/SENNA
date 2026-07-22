"""The X-Model-Version middleware: 5.11.2 wants the served version on every API
response without touching the 5.9.2 body shapes — errors included, because a
version-less 404 is still an answer someone will cache or screenshot (E-15).
"""

from tests.api.conftest import CIRCUIT

ROUTES = (
    "/api/v1/health",
    "/api/v1/circuits",
    f"/api/v1/circuits/{CIRCUIT}",
    "/api/v1/agents",
    f"/api/v1/tyres/{CIRCUIT}",
)


def test_every_routed_response_carries_the_served_version(client):
    for route in ROUTES:
        response = client.get(route)
        assert response.headers.get("X-Model-Version"), f"{route} lost the version header"


def test_error_responses_carry_it_too(client):
    response = client.get("/api/v1/circuits/nowhere_grand_prix")
    assert response.status_code == 404
    assert response.headers.get("X-Model-Version")
