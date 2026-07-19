"""The engineer-heuristic baseline (A-07): a readable pit wall. Weather first, then the
cheap safety-car stop, then the mandatory second compound, then the tyre-degradation
trigger — and a SOC-aware energy mode underneath. Every threshold is a named constant in
configs/baselines.yaml, except the wetness bands, which it reads from env.yaml
compound_validity — the same source the action mask reads, so the two can never disagree
(E-08).
"""

import numpy as np

from senna.env import dynamics
from senna.env.scenario import COMPOUNDS, compound_code

_STAY_OUT = 0
_START = compound_code("MEDIUM")  # the env fixes everyone's grid tyre
_SLICKS = (compound_code("SOFT"), compound_code("MEDIUM"), compound_code("HARD"))
_INTER, _WET = compound_code("INTERMEDIATE"), compound_code("WET")


class EngineerHeuristic:
    def __init__(self, scenario, cfg: dict):
        self._scenario = scenario
        self._total_laps = scenario.total_laps
        # read eagerly so a config missing a threshold fails at construction, never silently
        self._deg_threshold_s = cfg["deg_pit_threshold_s"]
        self._min_stint = cfg["min_stint_laps"]
        self._forced_laps_left = cfg["forced_compound_laps_left"]
        self._sc_min_age = cfg["sc_pit_min_age_laps"]
        self._vsc_min_age = cfg["vsc_pit_min_age_laps"]
        wheel = cfg["compound_by_laps_left"]
        self._hard_min_laps = wheel["hard_min_laps"]
        self._medium_min_laps = wheel["medium_min_laps"]
        modes = cfg["modes"]
        self._conserve_soc_mj = modes["conserve_soc_mj"]
        self._attack_soc_mj = modes["attack_soc_mj"]
        self._attack_gap_s = modes["attack_gap_s"]
        self._defend_gap_s = modes["defend_gap_s"]
        validity = scenario.env["compound_validity"]
        self._slick_max = validity["slick_max_wetness"]
        self._wet_min = validity["wet_min_wetness"]

    def reset(self, obs, info, *, rng=None) -> None:
        self._compound = _START
        self._second_used = False
        self._stint_start = 0  # the lap the current stint began

    def act(self, obs, info, mask) -> np.ndarray:
        lap = info["lap"]
        if info["events"]["red_flag"] or info["events"]["forced_pit"]:
            self._stint_start = lap  # the env reset this car's tyre age
        age = lap - self._stint_start

        head = self._decide_pit(info, mask, age)
        if head >= 1 and mask[head]:
            self._compound = head - 1
            self._second_used |= self._compound != _START
            self._stint_start = lap
        else:
            head = _STAY_OUT
        return np.array([head, self._decide_mode(info, mask)])

    def _decide_pit(self, info, mask, age) -> int:
        wetness = info["events"]["wetness"]
        laps_left = self._total_laps - info["lap"]
        on_slick = self._compound in _SLICKS

        # weather first (E-08): get onto a tyre that suits the track
        if on_slick and wetness > self._slick_max:
            return self._wet_target(wetness, mask)
        if not on_slick and wetness <= self._slick_max:
            return self._dry_target(laps_left, mask)
        if self._compound == _INTER and wetness >= self._wet_min:
            return _WET + 1 if mask[_WET + 1] else _STAY_OUT

        # the cheap stop under a neutralisation (E-03): a set old enough takes it
        status = info["track_status"]
        if status == "sc" and age >= self._sc_min_age and laps_left > 1:
            return self._dry_target(laps_left, mask)
        if status == "vsc" and age >= self._vsc_min_age and laps_left > 1:
            return self._dry_target(laps_left, mask)

        # two-compound backstop (F-20): serve the second compound before it is too late
        dry = wetness <= self._slick_max
        if dry and not self._second_used and laps_left <= self._forced_laps_left:
            return self._dry_target(laps_left, mask)

        # the ordinary degradation trigger — only slicks carry a fitted deg curve
        if dry and self._compound in _SLICKS:
            deg_s = dynamics.tyre_deg_s(
                self._scenario.t0_s, self._scenario.deg_a[COMPOUNDS[self._compound]],
                self._scenario.deg_b[COMPOUNDS[self._compound]], age,
            )
            if deg_s >= self._deg_threshold_s and age >= self._min_stint and laps_left > 1:
                return self._dry_target(laps_left, mask)
        return _STAY_OUT

    def _dry_target(self, laps_left, mask) -> int:
        """The pit-wall compound wheel: a harder tyre for a longer run home. Honours the
        two-compound rule by never refitting the start compound while it is still owed."""
        if laps_left >= self._hard_min_laps:
            want = compound_code("HARD")
        elif laps_left >= self._medium_min_laps:
            want = compound_code("MEDIUM")
        else:
            want = compound_code("SOFT")
        if not self._second_used and want == _START:
            want = compound_code("HARD")
        head = want + 1
        if mask[head]:
            return head
        for candidate in (compound_code("HARD"), compound_code("MEDIUM"), compound_code("SOFT")):
            if mask[candidate + 1]:
                return candidate + 1
        return _STAY_OUT

    def _wet_target(self, wetness, mask) -> int:
        if wetness >= self._wet_min and mask[_WET + 1]:
            return _WET + 1
        if mask[_INTER + 1]:
            return _INTER + 1
        return _WET + 1 if mask[_WET + 1] else _STAY_OUT

    def _decide_mode(self, info, mask) -> int:
        soc = info["energy"]["soc_mj"]
        gap_ahead, gap_behind = info["gap_ahead_s"], info["gap_behind_s"]
        if soc < self._conserve_soc_mj:
            return dynamics.CONSERVE
        if 0.0 < gap_behind < self._defend_gap_s and mask[6 + dynamics.DEFEND]:
            return dynamics.DEFEND
        chasing = 0.0 < gap_ahead < self._attack_gap_s
        if chasing and soc >= self._attack_soc_mj and mask[6 + dynamics.ATTACK]:
            return dynamics.ATTACK
        return dynamics.BALANCED
