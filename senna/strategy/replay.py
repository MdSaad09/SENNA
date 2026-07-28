"""The replayed-real baseline (A-07): a real race's recorded stops, run against the 2026
physics. It runs balanced modes everywhere — a 2024 strategy carries no 2026 energy
decision, and inventing one would fabricate the very thing M2 measures. When the mask
blocks a recorded stop (a slick call on a wet track) it defers a few laps, then snaps to
the nearest legal compound and counts the deviation, so the comparison stays honest about
where reality and the simulator part ways.
"""

import numpy as np

from senna.env.scenario import compound_code
from senna.strategy.plans import _MODE_BY_NAME, PitPlan


def load_real_plan(circuit: str, *, season: int | None = None, driver: str | None = None,
                   configs_dir=None) -> PitPlan:
    """A recorded strategy from configs/real_strategies.yaml (checked in, so a rollout
    never needs the database). Entries are keyed season_circuit_driver because M2 carries
    two British GPs; a bare circuit resolves only while it is unambiguous, and an
    ambiguous one is refused with the candidate keys — silently picking either race
    would replay the wrong strategy under the right name. Stops are stored already
    mapped to the sim distance."""
    from senna import config

    recorded = config.load("real_strategies", configs_dir)
    matches = {
        key: entry for key, entry in recorded.items()
        if entry["circuit"] == circuit
        and (season is None or entry["season"] == season)
        and (driver is None or entry["driver"] == driver)
    }
    if not matches:
        wanted = "_".join(str(part) for part in (season, circuit, driver) if part)
        raise LookupError(f"real_strategies.yaml records no race matching {wanted} — "
                          "run senna.strategy.extract --write for it")
    if len(matches) > 1:
        raise LookupError(
            f"{circuit} has {len(matches)} recorded races ({', '.join(sorted(matches))}) — "
            "pass season= and driver= to pick one"
        )
    (entry,) = matches.values()
    return PitPlan(stops=tuple((int(lap), str(name)) for lap, name in entry["stops"]))


class RealStrategyReplay:
    def __init__(self, plan: PitPlan, scenario, cfg: dict):
        self._plan = plan
        self._scenario = scenario
        self._mode = _MODE_BY_NAME[cfg["mode"]]
        self._defer_max = cfg["defer_max_laps"]
        self.snapped = 0

    def reset(self, obs, info, *, rng=None) -> None:
        self._pending = list(self._plan.stops)
        self.snapped = 0

    def act(self, obs, info, mask) -> np.ndarray:
        head = self._resolve_stop(info, mask)
        return np.array([head, self._mode])

    def _resolve_stop(self, info, mask) -> int:
        if not self._pending:
            return 0
        stop_lap, name = self._pending[0]
        upcoming = info["lap"] + 1
        if upcoming < stop_lap:
            return 0

        requested = compound_code(name) + 1
        if mask[requested]:
            self._pending.pop(0)
            return requested
        if upcoming - stop_lap < self._defer_max:
            return 0  # give the track a few laps to allow the recorded tyre
        self._pending.pop(0)
        self.snapped += 1
        return self._snap(requested, mask)

    def _snap(self, requested: int, mask) -> int:
        """The nearest legal compound to the one recorded, ties toward the harder set."""
        legal = [head for head in range(1, 6) if mask[head]]
        if not legal:
            return 0
        return min(legal, key=lambda head: (abs(head - requested), -head))
