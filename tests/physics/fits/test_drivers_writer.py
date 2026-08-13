"""configs/drivers.yaml — the anti-black-box artifact for driver identity (F17).

The file is a list of numbers about named real people, so every leaf has to survive "how
do you know that?", and the honest answers include "I don't, so it is 1.0". That is what
the origin tags are for, and the writer refuses an untagged one rather than leaving it to
review. Nothing new emits it: the tree is `(value, origin)` pairs rendered by
`params_writer.render_params` with a different header, so the byte-determinism
physics_params.yaml already has comes for free — provided the builder hands the renderer
a tree it can sort.
"""

from dataclasses import replace

import numpy as np
import pytest
import yaml

from senna.physics.fits import run as fits_run
from senna.physics.fits.joint_pace import JointPaceFit
from senna.physics.fits.params_writer import render_params, validate_complete, validate_origins
from senna.physics.fits.tyre_style import DegStyleFit

ERA = "2024"
GENERATED_AT = "seasons 2022-2026, round 6"

# configs/fits.yaml driver_identity.min_laps_for_seat_pace: below this a driver-by-circuit
# cell is too thin to publish per circuit and the driver takes their own mean instead
MIN_LAPS_FOR_SEAT_PACE = 30

# centred within each circuit, as the regression delivers them (see joint_pace)
BAHRAIN_EFFECTS_S = {"VER": -0.42, "HAM": 0.31, "LEC": 0.11}
MONACO_EFFECTS_S = {"VER": -0.30, "HAM": 0.22, "LEC": 0.08}
BAHRAIN_LAPS = {"VER": 213, "HAM": 198, "LEC": 205}
MONACO_LAPS = {"VER": 96, "HAM": 21, "LEC": 88}  # HAM retired early both years

# one clean lap, and an effect the size of a pit stop. Real: japanese_grand_prix era 2024
# has BOT at +21.57 s off a single lap. A level like this sets the centring mean in the
# regression and is then dropped by the lap gate, which displaces every cell that survives.
ONE_LAP_OUTLIER = {"BOT": (21.57, 1)}


def _joint(effects_s, laps, *, seasons=(2022, 2023, 2024, 2025)) -> JointPaceFit:
    """A fit carrying only what the driver tree reads off it."""
    return JointPaceFit(
        t0_s=92.0, k_m_s_per_kg=0.031, k_m_se_s_per_kg=0.002, evolution_s_per_lap=-0.01,
        trend_s_per_lap=-0.02, identified=True, vif_fuel=5.0, condition_number=10.0,
        sigma_driver_s=0.31, compound_offsets_s={}, t_ref_s=92.0, s_ref_s=1.0,
        n_laps=sum(laps.values()), n_excluded_no_tyre_age=0,
        seasons_fitted=seasons,
        driver_effects_s=effects_s,
        driver_laps=laps,
        driver_seasons=dict.fromkeys(effects_s, seasons),
    )


def _tree(outlier: dict | None = None) -> dict:
    """The driver tree as `run.py` assembles it before the write gates see it.

    `outlier` adds {code: (effect_s, laps)} to the Bahrain fit, for the centring test.
    """
    bahrain_effects_s = dict(BAHRAIN_EFFECTS_S)
    bahrain_laps = dict(BAHRAIN_LAPS)
    for code, (effect_s, laps) in (outlier or {}).items():
        bahrain_effects_s[code], bahrain_laps[code] = effect_s, laps
    # centre over every level, which is what the regression hands the tree
    # (joint_pace._centred_effects) — and the whole point is that "every level" includes
    # the one the lap gate is about to drop. Without this the fixture arrives pre-centred
    # on the survivors, the displacement never happens, and the centring test below passes
    # against an implementation that does nothing.
    mean_s = sum(bahrain_effects_s.values()) / len(bahrain_effects_s)
    bahrain_effects_s = {code: v - mean_s for code, v in bahrain_effects_s.items()}
    joint = {
        ("bahrain_grand_prix", ERA): _joint(bahrain_effects_s, bahrain_laps),
        ("monaco_grand_prix", ERA): _joint(MONACO_EFFECTS_S, MONACO_LAPS),
    }
    style: dict = {
        ERA: {
            "VER": DegStyleFit(mult=0.94, se=0.031, rel_se=0.033, n_stints=41,
                               n_laps=2871, identified=True),
            # too few stints to separate a style from noise, so 1.0 and flagged
            "HAM": DegStyleFit(mult=1.0, se=0.42, rel_se=0.42, n_stints=9,
                               n_laps=310, identified=False),
            "LEC": DegStyleFit(mult=1.06, se=0.048, rel_se=0.045, n_stints=37,
                               n_laps=2604, identified=True),
        }
    }
    return fits_run.driver_tree(joint, style, min_laps_for_seat_pace=MIN_LAPS_FOR_SEAT_PACE)


def test_every_driver_constant_declares_its_origin():
    tree = _tree()

    validate_origins(tree)  # every leaf names where it came from
    # and none of them is null: the old spec proposed a `fallback.pace_s: null` leaf, which
    # this same gate would have refused. An unnamed seat is code behaviour, not a constant.
    validate_complete(tree)

    verstappen = tree["drivers"]["VER"][2024]
    hamilton = tree["drivers"]["HAM"][2024]
    assert verstappen["deg_mult"][0] == 0.94
    assert verstappen["deg_mult"][1].startswith("fitted")
    # the honest tag on the honest value: an unidentified multiplier is a choice, not a
    # measurement, and it must not reach the yaml wearing a `fitted` tag (E-10)
    assert hamilton["deg_mult"][0] == 1.0
    assert hamilton["deg_mult"][1].startswith("stylised")
    assert hamilton["deg_mult_identified"][0] is False
    # the seasons say which seat the number measures, which is the answer that survives
    # "so you measured Verstappen's skill?" — era 2024 pools four cars, not one driver
    assert verstappen["seasons"][0] == [2022, 2023, 2024, 2025]


def test_a_cell_below_the_lap_gate_is_not_published():
    tree = _tree()

    # E-10 one layer down: a coefficient the design could not pin down is not published,
    # and 21 laps of Monaco cannot pin down a seat. The driver keeps their mean over the
    # circuits that did clear the gate, which is what the resolver falls back to.
    assert set(tree["drivers"]["HAM"][2024]["seat_pace_s"]) == {"bahrain_grand_prix"}
    assert set(tree["drivers"]["VER"][2024]["seat_pace_s"]) == {
        "bahrain_grand_prix", "monaco_grand_prix"
    }
    # dropping HAM's Monaco cell re-centres what is left of that column, so VER's Monaco
    # number is his effect against the two seats that survived rather than against all
    # three. Bahrain keeps every seat and does not move.
    monaco_centre_s = (MONACO_EFFECTS_S["VER"] + MONACO_EFFECTS_S["LEC"]) / 2
    verstappen_mean_s = (
        BAHRAIN_LAPS["VER"] * BAHRAIN_EFFECTS_S["VER"]
        + MONACO_LAPS["VER"] * (MONACO_EFFECTS_S["VER"] - monaco_centre_s)
    ) / (BAHRAIN_LAPS["VER"] + MONACO_LAPS["VER"])
    assert tree["drivers"]["VER"][2024]["seat_pace_mean_s"][0] == pytest.approx(
        verstappen_mean_s, abs=5e-4
    )


def _column_s(tree: dict, circuit: str) -> list[float]:
    return [
        eras[2024]["seat_pace_s"][circuit][0]
        for eras in tree["drivers"].values()
        if circuit in eras.get(2024, {}).get("seat_pace_s", {})
    ]


def test_a_published_column_is_centred_on_the_cells_that_survived_the_gate():
    """The centring test that matters, and the one the fit-level assertion cannot make.

    The regression centres over every driver in the design, so its effects sum to zero with
    the outlier included — `test_driver_effects_are_centred` will happily pass while the
    published file is displaced. The gate then removes the level that set the centre, and a
    one-lap level carries the largest effect there is, so the two steps conspire: every
    surviving cell at that circuit moves by the dropped level's share.

    Left uncorrected this published 22 claims at japanese_grand_prix era 2024 that were each
    about 0.95 s too fast, and it broke the property M1 leans on — a named seat must be
    drawn from the same distribution as the N(0, sigma_driver_s) an unnamed seat gets.
    """
    clean = _tree()
    poisoned = _tree(ONE_LAP_OUTLIER)

    assert np.mean(_column_s(clean, "bahrain_grand_prix")) == pytest.approx(0.0, abs=1e-9)
    # the outlier is gated out of the file entirely...
    assert "BOT" not in poisoned["drivers"]
    # ...and taking it out of the centring too is what keeps the survivors where they were
    assert np.mean(_column_s(poisoned, "bahrain_grand_prix")) == pytest.approx(0.0, abs=1e-9)
    assert _column_s(poisoned, "bahrain_grand_prix") == pytest.approx(
        _column_s(clean, "bahrain_grand_prix")
    )


def test_a_refusal_publishes_the_number_that_explains_it():
    tree = _tree()
    hamilton = tree["drivers"]["HAM"][2024]

    # the count gate rarely bites, so `n_stints: 9` beside `deg_mult_identified: false` is
    # not the reason — the precision gate is, and a refusal nobody can audit from the file
    # is a black box wearing a flag (E-10)
    assert hamilton["deg_mult_rel_se"][0] == 0.42
    # the two samples differ and sit next to each other, so both are named
    assert hamilton["n_laps"][1].endswith("the seat-pace sample")
    assert hamilton["deg_mult_n_laps"][1].endswith("the tyre-style sample")


def test_an_identified_2026_fit_carries_the_ar_10_grade():
    """A driver coefficient meets a fuel column only where the circuit's attribution was
    identified — an unidentified fit refits without it. Where it did, the 2026 fuel mass is
    AR-10 grade C, and the flag has to travel with the value the way it does on t0_s."""
    fit = _joint(BAHRAIN_EFFECTS_S, BAHRAIN_LAPS, seasons=(2026,))
    unidentified = replace(_joint(MONACO_EFFECTS_S, MONACO_LAPS, seasons=(2026,)),
                           identified=False)

    tree = fits_run.driver_tree(
        {("bahrain_grand_prix", "2026"): fit, ("monaco_grand_prix", "2026"): unidentified},
        {}, min_laps_for_seat_pace=MIN_LAPS_FOR_SEAT_PACE,
    )

    cells = tree["drivers"]["VER"][2026]["seat_pace_s"]
    assert "grade C via AR-10 fuel" in cells["bahrain_grand_prix"][1]
    # and not where the fuel column was spliced out of the design
    assert "grade C" not in cells["monaco_grand_prix"][1]
    # the seasons ride the cell, because a circuit can only carry the seasons it was raced in
    assert "season(s) 2026" in cells["bahrain_grand_prix"][1]


def test_drivers_yaml_renders_byte_deterministically():
    header = "# SENNA — fitted driver identity (F17).\n"

    first = render_params(_tree(), generated_at=GENERATED_AT, header=header)
    second = render_params(_tree(), generated_at=GENERATED_AT, header=header)

    # `git diff` after a make fit rerun must be empty, which is what makes the committed
    # table checkable against the data that produced it (A-09)
    assert first == second

    loaded = yaml.safe_load(first)
    # era keys render unquoted and load back as ints, matching physics_params.yaml and
    # the `era_int` scenario.py indexes with — quoted, every lookup would miss
    assert 2024 in loaded["drivers"]["VER"]
    assert loaded["drivers"]["VER"][2024]["seat_pace_s"]["bahrain_grand_prix"] == pytest.approx(
        BAHRAIN_EFFECTS_S["VER"]
    )
