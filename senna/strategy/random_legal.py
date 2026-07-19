"""The random-legal baseline (A-07): sample uniformly among the actions the mask permits,
per head. By construction it can never propose an illegal action — the same
compliance-by-construction the env guarantees (F-16), seen from the policy side. It is the
floor a strategy must beat, and it also drives the throughput benchmark (5.6.2).
"""

import numpy as np


class RandomLegal:
    def __init__(self):
        self._rng = None

    def reset(self, obs, info, *, rng) -> None:
        self._rng = rng

    def act(self, obs, info, mask) -> np.ndarray:
        return np.array([self._pick(mask[:6]), self._pick(mask[6:])])

    def _pick(self, head) -> int:
        return int(self._rng.choice(np.flatnonzero(head)))
