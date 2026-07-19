"""Pit plans and the greedy energy schedule — the shared vocabulary of the baselines and
the oracle. A PitPlan is a bare list of (lap, compound) stops; a PlanPolicy executes one
through the ego action interface; greedy_mode is the per-lap pace-optimal energy choice,
priced against the env's own dynamics so the oracle never drifts from the physics it
optimises (5.12 M3).
"""

from dataclasses import dataclass

import numpy as np

from senna.env import dynamics, events
from senna.env.scenario import compound_code

_MODE_BY_NAME = {"conserve": 0, "balanced": 1, "attack": 2, "defend": 3}
_STATUS_CODE = {"green": events.GREEN, "vsc": events.VSC, "sc": events.SC, "red": events.RED}


@dataclass(frozen=True)
class PitPlan:
    stops: tuple  # ((lap, compound_name), ...) — the out-lap and the tyre taken


def greedy_mode(soc_mj: float, track_status: int, mask: np.ndarray, scenario) -> int:
    """The legal energy mode with the lowest lap-time price this lap, evaluated straight
    from dynamics.resolve_energy / mode_pace_s so it agrees with the env exactly. Ties go to
    balanced — the do-no-harm default (A-05 greedy energy schedule)."""
    modes = np.arange(4)
    harvest = np.full(4, dynamics.per_lap_harvest_mj(scenario, track_status))
    request = dynamics.deploy_request_mj(modes, scenario)
    delivered, derate, _ = dynamics.resolve_energy(np.full(4, soc_mj), harvest, request, scenario)
    price = dynamics.mode_pace_s(modes, delivered, request, scenario) + derate

    legal = mask[6:]
    best_mode, best_key = None, None
    for mode in range(4):
        if not legal[mode]:
            continue
        key = (price[mode], mode != dynamics.BALANCED, mode)  # price, then prefer balanced
        if best_key is None or key < best_key:
            best_key, best_mode = key, mode
    return best_mode


class PlanPolicy:
    """Runs a fixed PitPlan: box onto the planned compound on its out-lap (unless the mask
    forbids it — the plan only requests), otherwise stay out. Energy mode is the greedy
    per-lap optimum, or a fixed mode named or coded."""

    def __init__(self, plan: PitPlan, *, mode="greedy", scenario=None):
        self._plan = plan
        self._mode = mode
        self._scenario = scenario
        self._stops: dict[int, int] = {}

    def reset(self, obs, info, *, rng=None) -> None:
        self._stops = {lap: compound_code(name) + 1 for lap, name in self._plan.stops}

    def act(self, obs, info, mask) -> np.ndarray:
        head = self._stops.get(info["lap"] + 1, 0)
        if head and not mask[head]:
            head = 0
        return np.array([head, self._energy_mode(info, mask)])

    def _energy_mode(self, info, mask) -> int:
        if self._mode == "greedy":
            status = _STATUS_CODE[info["track_status"]]
            return greedy_mode(info["energy"]["soc_mj"], status, mask, self._scenario)
        if isinstance(self._mode, str):
            return _MODE_BY_NAME[self._mode]
        return int(self._mode)
