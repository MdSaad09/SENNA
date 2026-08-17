"""The robustness overlays and the direction logic.

The race rolling needs the frozen triplet and is exercised by running the study; what is
pinned here is everything that decides what an arm *means* — that an overlay moves one
field and nothing else, that the predicted direction is the one a strategist would name,
and that a null arm reports as a null rather than as agreement.
"""

import json

import pytest
import yaml

from senna import config
from senna.eval.robustness import (
    KNOBS,
    agreement,
    build_overlay,
    compare,
    expected_direction,
    first_stops,
)

CIRCUITS = ["chinese_grand_prix", "monaco_grand_prix"]


@pytest.fixture
def overlay_root(tmp_path):
    return tmp_path


def _params(path):
    return yaml.safe_load((path / "physics_params.yaml").read_text())


def test_the_degradation_arm_scales_only_the_a_coefficient(overlay_root):
    base = config.REPO_ROOT / "configs"
    dest = build_overlay(base_configs_dir=base, dest=overlay_root / "up",
                         knob="tyre_degradation", direction="up", circuits=CIRCUITS)
    before = _params(base)["circuits"]
    after = _params(dest)["circuits"]

    for slug in CIRCUITS:
        for era, block in (after[slug]["degradation"] or {}).items():
            for compound, fit in (block or {}).items():
                was = before[slug]["degradation"][era][compound]
                assert fit["a"] == pytest.approx(was["a"] * 1.10)
                assert fit["b"] == was["b"], "the exponent must not move"
        # a circuit the arm does not name is untouched
        assert after[slug]["pit_loss"] == before[slug]["pit_loss"]

    untouched = next(s for s in before if s not in CIRCUITS)
    assert after[untouched]["degradation"] == before[untouched]["degradation"]


def test_the_pit_loss_arm_shifts_only_the_mean(overlay_root):
    base = config.REPO_ROOT / "configs"
    dest = build_overlay(base_configs_dir=base, dest=overlay_root / "up",
                         knob="pit_loss", direction="up", circuits=CIRCUITS)
    before, after = _params(base)["circuits"], _params(dest)["circuits"]

    for slug in CIRCUITS:
        assert after[slug]["pit_loss"]["mean_s"] == pytest.approx(
            before[slug]["pit_loss"]["mean_s"] + KNOBS["pit_loss"]["delta"])
        assert after[slug]["pit_loss"]["sigma_s"] == before[slug]["pit_loss"]["sigma_s"]
        assert after[slug]["degradation"] == before[slug]["degradation"]


def test_a_pit_stop_can_never_be_made_to_cost_negative_time(overlay_root, monkeypatch):
    base = overlay_root / "base"
    base.mkdir()
    for name in ("physics_params.yaml",):
        source = (config.REPO_ROOT / "configs" / name).read_text()
        params = yaml.safe_load(source)
        params["circuits"][CIRCUITS[0]]["pit_loss"]["mean_s"] = 0.5
        (base / name).write_text(yaml.safe_dump(params))
    dest = build_overlay(base_configs_dir=base, dest=overlay_root / "down",
                         knob="pit_loss", direction="down", circuits=[CIRCUITS[0]])
    assert _params(dest)["circuits"][CIRCUITS[0]]["pit_loss"]["mean_s"] >= 1.0


def test_the_predicted_directions_are_the_ones_a_strategist_would_name():
    # harder wear, stop sooner; a more expensive stop, delay it
    assert expected_direction("tyre_degradation", "up") == "earlier"
    assert expected_direction("tyre_degradation", "down") == "later"
    assert expected_direction("pit_loss", "up") == "later"
    assert expected_direction("pit_loss", "down") == "earlier"


def test_agreement_counts_only_the_races_that_moved():
    baseline = {("a", 1): 20, ("a", 2): 20, ("a", 3): 20}
    arm = {("a", 1): 18, ("a", 2): 20, ("a", 3): 22}
    comparison = compare(baseline, arm)

    assert comparison["moved_earlier"] == 1
    assert comparison["moved_later"] == 1
    assert comparison["unchanged"] == 1
    assert agreement(comparison, "earlier") == pytest.approx(0.5)


def test_an_arm_that_moved_nothing_reports_no_agreement_rather_than_perfect():
    """The pit-loss arms moved zero of sixty races. That must read as 'no signal', not
    as 100% agreement with whatever was predicted."""
    baseline = {("a", 1): 20, ("a", 2): 25}
    comparison = compare(baseline, dict(baseline))
    assert comparison["unchanged"] == 2
    assert agreement(comparison, "later") is None


def test_a_race_that_never_pitted_is_dropped_rather_than_counted_as_lap_zero():
    baseline = {("a", 1): 20, ("a", 2): None}
    arm = {("a", 1): 18, ("a", 2): 30}
    comparison = compare(baseline, arm)
    assert comparison["n"] == 1, "a stintless race has no first stop to shift"


def test_first_stops_reads_the_opening_stop_per_race():
    class Result:
        def __init__(self, laps):
            self.pit_laps = laps

    rolled = {"monza": ([11, 22], [Result([14, 38]), Result([])])}
    assert first_stops(rolled) == {("monza", 11): 14, ("monza", 22): None}


def test_the_published_study_agrees_with_its_own_stored_arms():
    """If the committed payload has drifted from what the module computes, the doc is
    quoting numbers the code no longer produces."""
    path = config.REPO_ROOT / "docs" / "results" / "F14" / "store" / "robustness.json"
    if not path.is_file():
        pytest.skip("robustness study has not been run")
    payload = json.loads(path.read_text())["payload"]

    for label, arm in payload["arms"].items():
        assert arm["predicted"] == expected_direction(arm["knob"], arm["direction"]), label
        recomputed = agreement(arm, arm["predicted"])
        if arm["direction_agreement"] is None:
            assert recomputed is None, label
        else:
            assert recomputed == pytest.approx(arm["direction_agreement"]), label
