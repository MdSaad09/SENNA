"""The 5.9.2 request/response shapes as pure pydantic — no app, no services. The bounds
here are the API's outermost fence; the era-dependent grid bound (20 cars in 2024) is
mapping's job and lives in tests/serve/test_mapping.py.
"""

import pytest
from pydantic import ValidationError

from api.schemas import DecisionCard, LapFrame, SimulationCreate


def test_simulation_create_fills_the_specced_defaults():
    req = SimulationCreate(circuit_id="bahrain_grand_prix", grid_position=5)
    assert req.era == "2026"
    assert req.weather_profile == "dry"
    assert req.rival_band == "test"  # 5.9.2 default; the env's own default is "train"
    assert req.seed is None
    assert req.model_version is None


def test_grid_position_is_bounded_one_to_twenty_two():
    for slot in (1, 22):
        assert SimulationCreate(circuit_id="x", grid_position=slot).grid_position == slot
    for slot in (0, 23, -3):
        with pytest.raises(ValidationError):
            SimulationCreate(circuit_id="x", grid_position=slot)


def test_the_literal_fields_refuse_values_off_the_spec_list():
    with pytest.raises(ValidationError):
        SimulationCreate(circuit_id="x", grid_position=1, era="2025")
    with pytest.raises(ValidationError):
        SimulationCreate(circuit_id="x", grid_position=1, weather_profile="monsoon")
    with pytest.raises(ValidationError):
        SimulationCreate(circuit_id="x", grid_position=1, rival_band="eval")


def _car(car_id: int, position: int) -> dict:
    return {
        "id": car_id, "s_track": 0.25, "position": position, "compound": "MEDIUM",
        "tyre_age": 4, "gap_ahead_s": 1.2 if position > 1 else None, "in_pit": False,
    }


def test_lap_frame_validates_the_5_9_2_shape():
    frame = LapFrame.model_validate(
        {
            "lap": 12,
            "cars": [_car(i, i + 1) for i in range(22)],
            "agent": {
                "soc_mj": 2.4, "harvest_mj": 0.31, "deploy_mj": 0.55, "mode": 2,
                "action": {"pit": 0, "mode": 2}, "reward_terms": {"pace": -0.1},
                "mask_reasons": {"pit_soft": "unfitted compound"},
            },
            "events": [{"kind": "pit", "car_id": 7, "detail": "rival stop"}],
        }
    )
    assert frame.lap == 12
    assert len(frame.cars) == 22
    assert frame.events[0].kind == "pit"


def test_decision_card_accepts_the_f09_card_shape():
    # the exact dict senna.explain.cards.build_card emits (5.8.3) must pass through
    card = DecisionCard.model_validate(
        {
            "circuit": "bahrain_grand_prix",
            "lap": 23,
            "track_status": "green",
            "state": {"soc_frac": 0.5, "tyre_age_frac": 0.6},
            "masks": {"pit": [True] * 6, "mode": [True] * 4, "reasons": {}},
            "action": {"pit": 3, "mode": 1},
            "decision": "Lap 23 - pit for Hard, run balanced (probability 0.92)",
            "probs": {
                "pit": [0.0, 0.0, 0.04, 0.92, 0.02, 0.02],
                "mode": [0.1, 0.8, 0.05, 0.05],
            },
            "drivers": {"pit": [["tyre_age_frac", 0.4]], "mode": [["soc_frac", 0.2]]},
            "flip": ["would flip to stay out if gap_ahead_s were 0.4"],
            "plain_language": "Tyre age frac was the strongest push toward this call.",
            "honesty": {
                "fidelity": {"pit": 0.99, "mode": 0.99},
                "model_version": "senna-ppo-6b6edb78d84e-C-00835584",
                "statement": "not a causal claim",
            },
        }
    )
    assert card.lap == 23
    assert card.honesty["model_version"].startswith("senna-ppo-")
