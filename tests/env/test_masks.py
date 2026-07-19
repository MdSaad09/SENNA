"""Action-mask rules (5.5.2). Each rule is masked with its own reason code, and
no head is ever left all-False — MaskablePPO needs at least one legal action per
head. Reasons keys are "pit:k"/"mode:k" for each DISALLOWED action.
"""

import numpy as np

from senna.env import F1RaceEnv
from senna.env.masks import (
    INTER_OUTSIDE_DAMP,
    PIT_LANE_CLOSED,
    SLICK_ABOVE_WET,
    SOC_BELOW_ATTACK_FLOOR,
    TWO_COMPOUND_RULE,
    WET_NEEDS_WET,
    ActionMask,
    build_mask,
)
from tests.env.conftest import SEED

# a benign green, dry, mid-race state — every test overrides just the field it probes
VALIDITY = {"slick_max_wetness": 0.3, "inter_band": [0.25, 0.75], "wet_min_wetness": 0.7}


def _mask_kwargs(**overrides):
    base = dict(
        pit_open=True,
        weather=0,
        wetness=0.0,
        soc_mj=4.0,
        lap=10,
        total_laps=57,
        second_compound_used=True,
        attack_soc_floor_mj=0.5,
        validity=VALIDITY,
    )
    base.update(overrides)
    return base


def test_the_mask_exposes_two_boolean_heads_and_a_flat_view():
    mask = build_mask(**_mask_kwargs())

    assert isinstance(mask, ActionMask)
    assert mask.pit.shape == (6,)
    assert mask.mode.shape == (4,)
    assert mask.pit.dtype == bool
    assert mask.flat().shape == (10,)
    assert np.array_equal(mask.flat(), np.concatenate([mask.pit, mask.mode]))


def test_a_closed_pit_lane_masks_every_compound_but_leaves_stay_out():
    mask = build_mask(**_mask_kwargs(pit_open=False))

    assert mask.pit[0]  # stay-out survives a closed lane (F-20 has not fired)
    assert not mask.pit[1:].any()
    # at zero wetness a slick can only be masked because the lane is shut
    assert mask.reasons["pit:1"] == PIT_LANE_CLOSED
    assert mask.mode.all()


def test_slicks_are_masked_above_the_wet_threshold():
    mask = build_mask(**_mask_kwargs(wetness=0.5))

    assert not mask.pit[1]  # Soft
    assert not mask.pit[2]  # Medium
    assert not mask.pit[3]  # Hard
    assert mask.reasons["pit:1"] == SLICK_ABOVE_WET
    assert mask.pit[4]  # Inter valid inside the damp band at 0.5


def test_intermediate_is_masked_outside_the_damp_band():
    too_dry = build_mask(**_mask_kwargs(wetness=0.1))
    too_wet = build_mask(**_mask_kwargs(wetness=0.9))
    in_band = build_mask(**_mask_kwargs(wetness=0.5))

    assert not too_dry.pit[4]
    assert not too_wet.pit[4]
    assert too_dry.reasons["pit:4"] == INTER_OUTSIDE_DAMP
    assert in_band.pit[4]


def test_full_wet_is_masked_until_the_track_is_wet_enough():
    masked = build_mask(**_mask_kwargs(wetness=0.5))
    allowed = build_mask(**_mask_kwargs(wetness=0.8))

    assert not masked.pit[5]
    assert masked.reasons["pit:5"] == WET_NEEDS_WET
    assert allowed.pit[5]


def test_attack_is_masked_below_the_soc_floor():
    below = build_mask(**_mask_kwargs(soc_mj=0.4))
    above = build_mask(**_mask_kwargs(soc_mj=0.6))

    assert not below.mode[2]
    assert below.reasons["mode:2"] == SOC_BELOW_ATTACK_FLOOR
    assert above.mode[2]


def test_defend_is_never_masked():
    # defend is meaningful only with a car close behind, but it is never illegal
    for kwargs in (
        _mask_kwargs(soc_mj=0.0),
        _mask_kwargs(pit_open=False),
        _mask_kwargs(wetness=0.9),
    ):
        assert build_mask(**kwargs).mode[3]


def test_stay_out_is_masked_on_the_last_dry_pit_lap_without_a_second_compound():
    # F-20: the mandatory two-compound rule made structural, not a reward penalty
    mask = build_mask(
        **_mask_kwargs(second_compound_used=False, lap=56, total_laps=57)
    )

    assert not mask.pit[0]
    assert mask.reasons["pit:0"] == TWO_COMPOUND_RULE
    assert mask.pit[1:].any()  # a compound is still offered, so the head is not all-False


def test_the_two_compound_rule_only_fires_on_the_last_feasible_lap():
    early = build_mask(**_mask_kwargs(second_compound_used=False, lap=10, total_laps=57))
    already_used = build_mask(
        **_mask_kwargs(second_compound_used=True, lap=56, total_laps=57)
    )

    assert early.pit[0]  # plenty of laps left, no need to force the stop yet
    assert already_used.pit[0]  # the rule is already satisfied


def test_no_head_is_ever_left_all_false():
    states = [
        _mask_kwargs(),
        _mask_kwargs(pit_open=False),
        _mask_kwargs(wetness=1.0),
        _mask_kwargs(soc_mj=0.0),
        _mask_kwargs(second_compound_used=False, lap=56, total_laps=57),
        _mask_kwargs(pit_open=False, soc_mj=0.0, wetness=1.0),
    ]
    for kwargs in states:
        mask = build_mask(**kwargs)
        assert mask.pit.any()
        assert mask.mode.any()


def test_dry_slicks_outside_available_compounds_are_masked():
    # local import: the reason code is new with the F08 guard, and a top-level import
    # would stop this module's standing tests from collecting before it lands
    from senna.env.masks import UNFITTED_COMPOUND

    mask = build_mask(**_mask_kwargs(), fitted_slick_actions=frozenset({2, 3}))

    assert not mask.pit[1]  # Soft has no degradation fit here
    assert mask.reasons["pit:1"] == UNFITTED_COMPOUND
    assert mask.pit[2]
    assert mask.pit[3]

    # Suzuka 2026 fits only MEDIUM and HARD, so the env masks SOFT from reset
    env = F1RaceEnv("japanese_grand_prix", "2026")
    _, info = env.reset(seed=SEED)
    assert not info["mask"]["pit"][1]
    assert info["mask"]["reasons"]["pit:1"] == UNFITTED_COMPOUND


def test_fully_fitted_circuit_masks_are_unchanged():
    guarded = build_mask(**_mask_kwargs(), fitted_slick_actions=frozenset({1, 2, 3}))
    unguarded = build_mask(**_mask_kwargs())

    assert np.array_equal(guarded.pit, unguarded.pit)
    assert np.array_equal(guarded.mode, unguarded.mode)
    assert guarded.reasons == unguarded.reasons

    # Bahrain fits all three slicks: at a dry reset the guard changes nothing —
    # stay-out and every slick stay legal, and no slick carries a reason code
    env = F1RaceEnv("bahrain_grand_prix", "2026")
    _, info = env.reset(seed=SEED)
    assert info["mask"]["pit"][:4] == [True] * 4
    assert all(key not in info["mask"]["reasons"] for key in ("pit:1", "pit:2", "pit:3"))


def test_the_unfitted_rule_does_not_override_a_weather_reason():
    mask = build_mask(**_mask_kwargs(wetness=0.5), fitted_slick_actions=frozenset({2, 3}))

    assert not mask.pit[1]
    assert mask.reasons["pit:1"] == SLICK_ABOVE_WET  # first rule wins, guard stays quiet
