"""Per-head action masks (spec 5.5.2). Legality that is discrete lives here; legality
that is continuous (SOC, energy) lives in the dynamics clip. Together they make the
policy 100% compliant by construction (F-16) — every masked rule carries a reason code
so the decision cards can say why an option was off the table, and no head is ever left
all-False, which MaskablePPO forbids.
"""

from dataclasses import dataclass

import numpy as np

PIT_LANE_CLOSED = "pit_lane_closed"
SLICK_ABOVE_WET = "slick_above_wet_threshold"
INTER_OUTSIDE_DAMP = "inter_outside_damp_band"
WET_NEEDS_WET = "wet_requires_wet_track"
TWO_COMPOUND_RULE = "two_compound_rule"  # F-20
SOC_BELOW_ATTACK_FLOOR = "soc_below_attack_floor"

# pit head: 0 stay · 1 Soft · 2 Medium · 3 Hard · 4 Inter · 5 Wet
SLICK_ACTIONS = (1, 2, 3)
INTER_ACTION = 4
WET_ACTION = 5
ATTACK_MODE = 2


@dataclass(frozen=True)
class ActionMask:
    pit: np.ndarray
    mode: np.ndarray
    reasons: dict

    def flat(self) -> np.ndarray:
        return np.concatenate([self.pit, self.mode])


def build_mask(*, pit_open: bool, weather: int, wetness: float, soc_mj: float,
               lap: int, total_laps: int, second_compound_used: bool,
               attack_soc_floor_mj: float, validity: dict) -> ActionMask:
    pit = np.ones(6, dtype=bool)
    mode = np.ones(4, dtype=bool)
    reasons: dict[str, str] = {}

    if not pit_open:
        for action in (*SLICK_ACTIONS, INTER_ACTION, WET_ACTION):
            pit[action] = False
            reasons[f"pit:{action}"] = PIT_LANE_CLOSED
    else:
        if wetness > validity["slick_max_wetness"]:
            for action in SLICK_ACTIONS:
                pit[action] = False
                reasons[f"pit:{action}"] = SLICK_ABOVE_WET
        low, high = validity["inter_band"]
        if not (low <= wetness <= high):
            pit[INTER_ACTION] = False
            reasons[f"pit:{INTER_ACTION}"] = INTER_OUTSIDE_DAMP
        if wetness < validity["wet_min_wetness"]:
            pit[WET_ACTION] = False
            reasons[f"pit:{WET_ACTION}"] = WET_NEEDS_WET

    # F-20: on the last lap a dry race can still serve the mandatory second compound,
    # staying out is illegal — the rule is structural, not a reward penalty. It can only
    # fire with the lane open, so it never collides with the closed-lane mask above.
    dry = weather == 0 and wetness <= validity["slick_max_wetness"]
    if pit_open and dry and not second_compound_used and lap == total_laps - 1:
        pit[0] = False
        reasons["pit:0"] = TWO_COMPOUND_RULE

    if soc_mj < attack_soc_floor_mj:
        mode[ATTACK_MODE] = False
        reasons[f"mode:{ATTACK_MODE}"] = SOC_BELOW_ATTACK_FLOOR

    return ActionMask(pit=pit, mode=mode, reasons=reasons)
