"""/tyres mirrors the fitted degradation block verbatim — a, b, low_confidence and the
support columns, honesty included — and /energy replays a completed run's ledger inside
the physical bounds: SOC in [0, 4] MJ, h_max from configs/circuits.yaml (E-02).
"""

import os

import pytest

from senna import config
from tests.api.conftest import CIRCUIT, SEED, create_and_drain

pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("DATABASE_URL"),
        reason="needs Postgres; set DATABASE_URL (CI provides a service container)",
    ),
    pytest.mark.skipif(
        not os.environ.get("REDIS_URL"),
        reason="needs Redis; set REDIS_URL (CI provides a service container)",
    ),
]


def test_tyres_mirror_the_fitted_degradation_surfaces(client):
    fitted = config.load("physics_params")["circuits"][CIRCUIT]["degradation"]
    curves = client.get(f"/api/v1/tyres/{CIRCUIT}").json()

    served = {(curve["era"], curve["compound"]) for curve in curves}
    # yaml era keys parse as ints; the API speaks strings
    assert served == {(str(era), compound) for era, block in fitted.items() for compound in block}

    for curve in curves:
        params = fitted[int(curve["era"])][curve["compound"]]
        assert curve["circuit_id"] == CIRCUIT
        assert curve["a"] == pytest.approx(params["a"])
        assert curve["b"] == pytest.approx(params["b"])
        # the T5 cluster transfers say so themselves — the flag must survive the trip
        assert curve["low_confidence"] is params["low_confidence"]
        assert curve["max_age_seen"] == params.get("max_age_seen")
        assert curve["n_laps"] == params.get("n_laps")


@pytest.mark.slow
def test_energy_series_covers_every_lap_within_the_store_bounds(client, fresh_schema,
                                                                flush_redis):
    run_id = create_and_drain(client, {"circuit_id": CIRCUIT, "grid_position": 5, "seed": SEED})

    profile = client.get(f"/api/v1/energy/{run_id}").json()
    circuit_entry = config.load("circuits")[CIRCUIT]
    assert profile["run_id"] == run_id
    assert profile["circuit_id"] == CIRCUIT
    assert profile["h_max_mj"] == pytest.approx(circuit_entry["h_max_mj"])  # E-02
    assert [entry["lap"] for entry in profile["laps"]] == list(
        range(1, circuit_entry["race_laps"] + 1)
    )
    for entry in profile["laps"]:
        assert 0.0 <= entry["soc_mj"] <= 4.0  # the 4 MJ usable store, never 8
        assert entry["harvest_mj"] >= 0.0
        assert entry["deploy_mj"] >= 0.0
