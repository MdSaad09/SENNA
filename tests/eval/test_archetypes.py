"""The three-archetype slice, and the finding that came out of it.

Two things are pinned here. That the slice is a *slice* — same races, same seeds, no
re-run, so a per-archetype figure can always be traced back to the pairs it came from.
And the classification the conditional-advantage finding rests on, because that finding
is the results chapter's headline caveat and it must not drift silently when a refit
moves a circuit from one group to another.
"""

import json

import pytest

from senna import config
from senna.eval.archetypes import (
    ARCHETYPES,
    build,
    conditional_advantage,
    fit_provenance,
    m1_by_archetype,
)

STORE = config.REPO_ROOT / "docs" / "results" / "F14" / "store"

pytestmark = pytest.mark.skipif(
    not (STORE / "m1_pairs.json").is_file(),
    reason="needs the committed F14 store",
)


@pytest.fixture(scope="module")
def fits():
    return config.load("physics_params")["circuits"]


def test_the_three_archetypes_are_the_calibrated_circuits(fits):
    """Not a coincidence, and worth stating: the archetypes were chosen for having a
    tyre model fitted at the circuit, and that is exactly what `calibrated` means."""
    calibrated = {slug for slug in config.load("circuits")
                  if fit_provenance(slug, fits) == "calibrated"}
    assert calibrated == set(ARCHETYPES)


def test_the_two_pathological_circuits_are_classed_unusable(fits):
    """Miami's soft and hard fits are flagged low-confidence; Canada's three compounds
    decay identically, so the model cannot tell them apart. Both are native fits and
    neither can carry a strategy, which is why they are neither calibrated nor
    synthesised — and why the calibrated group is a fair comparison."""
    assert fit_provenance("miami_grand_prix", fits) == "unusable"
    assert fit_provenance("canadian_grand_prix", fits) == "unusable"


def test_a_transferred_slick_makes_a_circuit_synthesised(fits):
    assert fit_provenance("bahrain_grand_prix", fits) == "synthesised"


def test_the_slice_reuses_the_stored_pairs_rather_than_re_running():
    m1 = json.loads((STORE / "m1_pairs.json").read_text())["payload"]
    sliced = m1_by_archetype(m1, config.load("eval"))

    for slug, row in sliced.items():
        pairs = [p for p in m1["per_pair"] if p["circuit"] == slug]
        assert row["n"] == len(pairs), f"{slug} lost pairs in the slice"
        expected = sum(p["baseline"] - p["agent"] for p in pairs) / len(pairs)
        assert row["mean_delta"] == pytest.approx(expected)


def test_every_sliced_pair_is_accounted_for_in_the_headline():
    """The per-archetype pairs are a subset of the published 480 — nothing invented."""
    m1 = json.loads((STORE / "m1_pairs.json").read_text())["payload"]
    sliced = m1_by_archetype(m1, config.load("eval"))
    assert sum(row["n"] for row in sliced.values()) <= m1["n"]
    assert set(sliced) <= set(ARCHETYPES)


def test_the_advantage_is_larger_where_the_tyre_model_is_synthesised(fits):
    """The results chapter's central caveat, as an assertion.

    If a refit ever makes this false, the chapter is wrong and this should fail rather
    than let a stale claim ship."""
    m1 = json.loads((STORE / "m1_pairs.json").read_text())["payload"]
    m3 = json.loads((STORE / "m3_regret.json").read_text())["payload"]
    groups = conditional_advantage(m1, m3, fits)

    assert groups["synthesised"]["mean_delta"] > groups["calibrated"]["mean_delta"] + 1.0
    # and the mechanism: the agent under-stops relative to the optimum, everywhere,
    # but by more where the tyre model is real
    for group in ("calibrated", "synthesised"):
        row = groups[group]
        assert row["agent_stops"] < row["oracle_stops"], group
    calibrated_gap = groups["calibrated"]["oracle_stops"] - groups["calibrated"]["agent_stops"]
    synthesised_gap = groups["synthesised"]["oracle_stops"] - groups["synthesised"]["agent_stops"]
    assert calibrated_gap > synthesised_gap


def test_the_build_names_what_it_could_not_slice():
    payload = build(STORE)
    assert payload["bank_level_only"], "metrics without per-circuit detail must be named"
    assert "m9_failures" in payload["bank_level_only"]
    assert set(payload["sliced"]) >= {"m1_paired_position_delta", "m3_oracle_regret"}
