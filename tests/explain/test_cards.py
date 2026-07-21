"""The decision card (A-03, 5.8.3, 5.3.5): every field a recruiter-readable card
needs, JSON-serialisable for the agent_decisions JSONB, and the E-15 refusal — a
surrogate fitted to one checkpoint never explains another.
"""

import json

import numpy as np
import pytest

from senna import config
from senna.explain.attributions import top_drivers
from senna.explain.cards import VersionMismatchError, build_card
from senna.explain.dataset import DecisionRecord
from senna.explain.features import FEATURE_NAMES
from tests.explain.conftest import CIRCUIT, SEED

MODEL_VERSION = "senna-ppo-6b6edb78d84e-C-00835584"  # the promoted headline triplet (F08)
FIDELITY = {"pit": 0.93, "mode": 0.96}
FLIP_LINES = ["stays out until tyre_age_norm reaches 0.43 (about 17 laps)"]


def _record():
    obs = np.zeros(32, dtype=np.float32)
    obs[8] = 0.6
    pit_unmasked = np.array([0.5, 0.2, 0.1, 0.1, 0.05, 0.05])
    pit_masked = np.array([0.5, 0.2, 0.1, 0.1, 0.1, 0.0])  # the wet is off the table
    mode_unmasked = np.array([0.4, 0.3, 0.2, 0.1])
    mode_masked = np.array([0.5, 0.375, 0.0, 0.125])  # attack masked, renormalised
    mask = np.array([True, True, True, True, True, False, True, True, False, True])
    return DecisionRecord(
        obs=obs,
        pit_probs_unmasked=pit_unmasked, mode_probs_unmasked=mode_unmasked,
        pit_probs_masked=pit_masked, mode_probs_masked=mode_masked,
        mask=mask,
        reasons={"pit:5": "wet_requires_wet_track", "mode:2": "soc_below_attack_floor"},
        circuit=CIRCUIT, seed=SEED, lap=23, track_status="green",
        pit_action=0, mode_action=0,
    )


def _drivers(k):
    shap_row = np.zeros(32)
    shap_row[8] = 0.9    # tyre age dominates
    shap_row[14] = -0.6  # magnitude orders the ranking, sign is kept
    shap_row[0] = 0.3
    shap_row[17] = 0.2
    shap_row[13] = 0.1
    shap_row[30] = 0.05
    return top_drivers(shap_row, FEATURE_NAMES, k)


def test_card_schema_complete():
    top_k = config.get(config.load("explain"), "cards.top_k_drivers")
    assert top_k == 5  # sourced 5.8.3 / A-03
    record = _record()
    drivers = _drivers(top_k)
    assert len(drivers) == top_k
    assert drivers[0][0] == FEATURE_NAMES[8]  # ordered by attribution magnitude

    card = build_card(
        record, pit_drivers=drivers, mode_drivers=drivers, flip_lines=FLIP_LINES,
        fidelity=FIDELITY, model_version=MODEL_VERSION, surrogate_version=MODEL_VERSION,
    )

    # named state: every one of the 32 dims, keyed by its feature name
    assert set(card["state"]) == set(FEATURE_NAMES)
    assert card["state"][FEATURE_NAMES[8]] == pytest.approx(0.6)

    # masks with their reason codes, verbatim from the env info dict
    assert card["masks"]["pit"] == [True, True, True, True, True, False]
    assert card["masks"]["mode"] == [True, True, False, True]
    assert card["masks"]["reasons"] == record.reasons

    assert card["action"] == {"pit": 0, "mode": 0}

    # probs are the masked view — what the agent could actually do
    assert card["probs"]["pit"] == pytest.approx(record.pit_probs_masked)
    assert card["probs"]["mode"] == pytest.approx(record.mode_probs_masked)

    # per-head top-5 drivers, the flip line(s) and a plain-language line
    assert len(card["drivers"]["pit"]) == top_k
    assert len(card["drivers"]["mode"]) == top_k
    assert card["flip"] == FLIP_LINES
    assert isinstance(card["plain_language"], str) and card["plain_language"].strip()

    # the honesty footer: per-head fidelity badge plus the exact model it explains
    assert card["honesty"]["fidelity"] == FIDELITY
    assert card["honesty"]["model_version"] == MODEL_VERSION

    # context the persist writer keys rows on
    assert card["circuit"] == CIRCUIT
    assert card["lap"] == 23

    json.dumps(card)  # 5.3.5 stores the card as JSONB: numpy types must not leak out


def test_version_mismatch_refuses():
    ghost = "senna-ppo-aaaaaaaaaaaa-C-00000001"

    with pytest.raises(VersionMismatchError) as err:
        build_card(
            _record(), pit_drivers=_drivers(5), mode_drivers=_drivers(5),
            flip_lines=FLIP_LINES, fidelity=FIDELITY,
            model_version=ghost, surrogate_version=MODEL_VERSION,
        )

    # the refusal names both versions, so the operator can see which artifact is stale
    assert MODEL_VERSION in str(err.value)
    assert ghost in str(err.value)
