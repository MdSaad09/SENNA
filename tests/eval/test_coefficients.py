"""The M2 energy-coefficient sensitivity (F15 deliverable A3; eval.yaml's
sensitivity.energy_coefficients key has said "no reader yet" since F14).

The 2024 scenario borrows the 2026 energy-mode fit — conserve cost, attack gain,
derate penalty and the attack SOC floor (senna/env/scenario.py module note) — so M2's
ten races re-roll with that borrowed block at +/-50%, as a pair of throwaway config
overlays. What is pinned here is the harvest-cap discipline applied to the new module:
the overlays move exactly the four borrowed coefficients and not a byte more, and the
store writer refuses an unpaired comparison instead of recording it.
"""

import json
from pathlib import Path

import pytest
import yaml

from senna import config
from senna.eval.coefficients import build_overlays, write_m2_sensitivity

REPO_CONFIGS = config.REPO_ROOT / "configs"
# the F14-frozen perturbation whose reader F15 adds — never a local literal
PERTURBATION = float(
    config.load("eval")["sensitivity"]["energy_coefficients"]["perturbation"]
)
BORROWED = (
    "conserve_pace_cost_s_per_mj",
    "attack_pace_gain_s",
    "derate_penalty_s_per_mj",
    "attack_soc_floor_mj",
)


def test_the_overlays_scale_exactly_the_four_borrowed_coefficients(tmp_path):
    overlays = build_overlays(
        base_configs_dir=REPO_CONFIGS, tmp_root=tmp_path, perturbation=PERTURBATION
    )
    assert set(overlays) == {"up", "down"}

    base = yaml.safe_load((REPO_CONFIGS / "physics_2026.yaml").read_text())
    for label, factor in (("up", 1 + PERTURBATION), ("down", 1 - PERTURBATION)):
        overlaid = yaml.safe_load(
            (Path(overlays[label]) / "physics_2026.yaml").read_text()
        )
        for key in BORROWED:
            assert overlaid["fitted"][key] == pytest.approx(
                base["fitted"][key] * factor
            ), (label, key)
        # everything else in the file rides through untouched — dirty_air_threshold_s
        # is the 5.5.3 traffic constant, not part of the borrowed energy-mode fit
        rest_base = {**base, "fitted": {k: v for k, v in base["fitted"].items()
                                        if k not in BORROWED}}
        rest_over = {**overlaid, "fitted": {k: v for k, v in overlaid["fitted"].items()
                                            if k not in BORROWED}}
        assert rest_over == rest_base, label


def test_the_overlays_touch_no_other_config(tmp_path):
    overlays = build_overlays(
        base_configs_dir=REPO_CONFIGS, tmp_root=tmp_path, perturbation=PERTURBATION
    )

    for label in ("up", "down"):
        rewritten = [path.name for path in sorted(REPO_CONFIGS.glob("*.yaml"))
                     if (Path(overlays[label]) / path.name).read_bytes()
                     != path.read_bytes()]
        assert rewritten == ["physics_2026.yaml"], label


def _arm(mean_delta: float) -> dict:
    races = [
        {"season": 2024, "circuit": "bahrain_grand_prix", "driver": "VER"},
        {"season": 2023, "circuit": "british_grand_prix", "driver": "NOR"},
    ]
    return {"mean_delta": mean_delta, "n_races": len(races), "races": races}


def test_coefficient_sensitivity_writes_paired_arms(tmp_path):
    dropped = [[2024, "monaco_grand_prix", "LEC"]]  # both arms lost the same race
    path = write_m2_sensitivity(
        tmp_path,
        arms={"up": _arm(0.4), "down": _arm(-0.2)},
        dropped={"up": dropped, "down": dropped},
        perturbation=PERTURBATION,
        model_version="senna-ppo-test-C-00000001",
    )

    assert Path(path).name == "m2_sensitivity.json"  # the file the report reads
    stored = json.loads(Path(path).read_text())
    assert set(stored) == {"envelope", "payload"}
    assert stored["payload"]["perturbation"] == PERTURBATION
    assert set(stored["payload"]["arms"]) == {"up", "down"}
    # the store envelope discipline: a number nobody can trace is not evidence (A-09)
    assert {"model_versions", "config_hash", "seeds_fingerprint", "git_commit",
            "scope"} <= set(stored["envelope"])
    assert "senna-ppo-test-C-00000001" in stored["envelope"]["model_versions"].values()


def test_arms_that_dropped_different_races_are_refused(tmp_path):
    """The harvest study's guard, inherited: a retirement under one perturbation and
    not the other silently makes the arms different experiments, and a row written
    anyway would print under a paired claim."""
    with pytest.raises(ValueError, match="paired"):
        write_m2_sensitivity(
            tmp_path,
            arms={"up": _arm(0.4), "down": _arm(-0.2)},
            dropped={"up": [[2024, "monaco_grand_prix", "LEC"]], "down": []},
            perturbation=PERTURBATION,
            model_version="senna-ppo-test-C-00000001",
        )
    assert not list(tmp_path.glob("*.json"))  # the refusal left no bytes behind
