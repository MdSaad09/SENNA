"""SimulationCreate -> F1RaceEnv construction (senna.serve.mapping). The API's 404/422
translations sit on top of the typed errors raised here; the weather map is
serving.yaml's (dry -> dry, mixed/wet_risk -> markov, plan Q2).
"""

import pytest

from api.schemas import SimulationCreate
from senna.serve.mapping import GridBoundError, UnknownCircuitError, build_env
from tests.serve.conftest import CIRCUIT


def _request(**overrides) -> SimulationCreate:
    base = {"circuit_id": CIRCUIT, "grid_position": 5}
    return SimulationCreate(**{**base, **overrides})


def test_the_request_maps_onto_the_env_construction():
    env = build_env(_request(era="2026", rival_band="test", weather_profile="dry"))
    assert env.circuit == CIRCUIT
    assert env.era == "2026"
    assert env.n_cars == 22
    # the env records its constructor kwargs; rival_band must arrive explicitly because
    # the API default ("test") and the env default ("train") disagree (plan divergence 2)
    assert env._band == "test"
    assert env._weather_mode == "dry"


def test_the_train_band_passes_through_when_asked_for():
    assert build_env(_request(rival_band="train"))._band == "train"


def test_mixed_and_wet_risk_both_run_the_markov_weather_engine():
    # Q2: two profiles, one engine — the verbatim profile is echoed by the API instead
    for profile in ("mixed", "wet_risk"):
        assert build_env(_request(weather_profile=profile))._weather_mode == "markov"


def test_an_unknown_circuit_raises_the_typed_error():
    with pytest.raises(UnknownCircuitError):
        build_env(_request(circuit_id="nowhere_grand_prix"))


def test_the_2024_era_bounds_the_grid_at_twenty_cars():
    env = build_env(_request(era="2024", grid_position=20))
    assert env.n_cars == 20  # physics_2024 fields 20 cars (plan divergence 4)
    with pytest.raises(GridBoundError):
        build_env(_request(era="2024", grid_position=21))
