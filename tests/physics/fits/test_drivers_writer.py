"""configs/drivers.yaml — the anti-black-box artifact for driver identity (F17).

The file is a list of numbers about named real people, so every leaf has to survive "how
do you know that?", and the honest answers include "I don't, so it is 1.0". That is what
the origin tags are for, and the writer refuses an untagged one rather than leaving it to
review. Nothing new emits it: the tree is `(value, origin)` pairs rendered by
`params_writer.render_params` with a different header, so the byte-determinism
physics_params.yaml already has comes for free — provided the builder hands the renderer
a tree it can sort.
"""

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


def _tree() -> dict:
    """The driver tree as `run.py` assembles it before the write gates see it."""
    joint = {
        ("bahrain_grand_prix", ERA): _joint(BAHRAIN_EFFECTS_S, BAHRAIN_LAPS),
        ("monaco_grand_prix", ERA): _joint(MONACO_EFFECTS_S, MONACO_LAPS),
    }
    style = {
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
    verstappen_mean_s = (
        BAHRAIN_LAPS["VER"] * BAHRAIN_EFFECTS_S["VER"]
        + MONACO_LAPS["VER"] * MONACO_EFFECTS_S["VER"]
    ) / (BAHRAIN_LAPS["VER"] + MONACO_LAPS["VER"])
    assert tree["drivers"]["VER"][2024]["seat_pace_mean_s"][0] == pytest.approx(
        verstappen_mean_s, abs=5e-4
    )


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
