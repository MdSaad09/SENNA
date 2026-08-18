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


def test_the_archetypes_are_repaired_and_nothing_is_calibrated(fits):
    """The archetypes were chosen for having a tyre model fitted at the circuit. Since
    F24 that means the `repaired` class — every slick carries the circuit's own data,
    with the soft's shape from the repair ladder because its wear was unidentifiable
    even pooled. And no 2026 circuit is `calibrated` any more: asserting the empty set
    is the honest statement of the era's data, and this failing means either a richer
    2026 season arrived (move the archetypes conversation on) or the classifier broke."""
    by_class = {slug: fit_provenance(slug, fits) for slug in config.load("circuits")}
    assert all(by_class[slug] == "repaired" for slug in ARCHETYPES)
    assert "calibrated" not in by_class.values()


def test_an_unrepaired_thin_fit_is_still_unusable(fits):
    """Miami's own medium and hard are flagged low-confidence and no repair touched
    them (the ladder only replaces unidentified fits), so the circuit still cannot
    carry a strategy claim. Canada moved: its identical-decay compounds were exactly
    the bound-clip F24 repairs, so it now classes `repaired` rather than unusable."""
    assert fit_provenance("miami_grand_prix", fits) == "unusable"
    assert fit_provenance("canadian_grand_prix", fits) == "repaired"


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

    assert groups["synthesised"]["mean_delta"] > groups["repaired"]["mean_delta"] + 1.0
    # the mechanism moved with F24 — the pre-repair agent under-stopped everywhere;
    # the retrained one over-stops on the measured circuits instead. What must stay
    # true is the split itself, plus the direction on each side of it.
    assert groups["repaired"]["agent_stops"] > groups["repaired"]["oracle_stops"]
    assert groups["synthesised"]["agent_stops"] > groups["synthesised"]["oracle_stops"]


def test_the_build_names_what_it_could_not_slice():
    payload = build(STORE)
    assert payload["bank_level_only"], "metrics without per-circuit detail must be named"
    assert "m9_failures" in payload["bank_level_only"]
    assert set(payload["sliced"]) >= {"m1_paired_position_delta", "m3_oracle_regret"}
