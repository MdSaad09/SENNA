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


def test_tyres_serve_cliff_age_and_transfer_donors(client):
    env_cfg = config.load("env")
    margin = env_cfg["tyre_failure"]["cliff_age_margin_laps"]
    fallback = env_cfg["obs"]["tyre_age_norm_laps"]
    fitted = config.load("physics_params")["circuits"][CIRCUIT]["degradation"]
    curves = client.get(f"/api/v1/tyres/{CIRCUIT}").json()

    for curve in curves:
        params = fitted[int(curve["era"])][curve["compound"]]
        # the T5 donor string survives to the dashboard, or is null for a direct fit
        assert curve["source_circuit"] == params.get("source_circuit")
        # the served cliff is the sim's boundary, built from configs — never a literal;
        # a transfer with no max_age_seen falls back to the horizon (E-09)
        assert curve["cliff_age"] == params.get("max_age_seen", fallback) + margin


def test_tyres_404_for_a_circuit_without_a_fitted_block(client):
    # french_grand_prix carries hazards but no degradation fits — the view's empty state
    assert client.get("/api/v1/tyres/french_grand_prix").status_code == 404


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


@pytest.mark.slow
def test_energy_profile_serves_usable_soc_and_modes(client, fresh_schema, flush_redis):
    run_id = create_and_drain(client, {"circuit_id": CIRCUIT, "grid_position": 5, "seed": SEED})

    profile = client.get(f"/api/v1/energy/{run_id}").json()
    usable = config.load("physics_2026")["energy_store"]["usable_capacity_mj"]
    assert profile["usable_soc_mj"] == pytest.approx(usable)  # the 4 MJ store, served

    for entry in profile["laps"]:
        assert set(entry) >= {"lap", "harvest_mj", "deploy_mj", "soc_mj", "mode", "pit"}
        assert 0 <= entry["mode"] <= 3           # the four energy modes
        assert entry["pit"] >= 0                  # 0 = stay out, 1-5 = compound code + 1
        assert 0.0 <= entry["soc_mj"] <= profile["usable_soc_mj"]
