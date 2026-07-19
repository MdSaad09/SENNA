"""The strategy-policy interface every baseline, the oracle plan runner and the agent's
evaluation harness share. A policy sees exactly what the agent sees — the observation, the
info dict and the flat action mask — and returns a MultiDiscrete([6, 4]) action the mask
permits. It never reaches into env internals; anything it needs to remember (its stint
age, the compounds it has run) it keeps itself, the way a real pit wall does.
"""

from typing import Protocol

import numpy as np


class StrategyPolicy(Protocol):
    def reset(self, obs, info, *, rng) -> None: ...

    def act(self, obs, info, mask) -> np.ndarray: ...


class ScriptedActions:
    """Replays a recorded action list, then holds station (stay out, balanced). The tool
    that drives a twin to a branch point before an afterstate search (M5 groundwork)."""

    def __init__(self, actions):
        self._actions = [np.asarray(a) for a in actions]
        self._i = 0

    def reset(self, obs, info, *, rng=None) -> None:
        self._i = 0

    def act(self, obs, info, mask) -> np.ndarray:
        if self._i < len(self._actions):
            action = self._actions[self._i]
            self._i += 1
            return action
        return np.array([0, 1])
