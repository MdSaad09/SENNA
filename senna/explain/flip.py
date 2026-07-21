"""Counterfactual flip probes (5.8.2): one feature swept across its physical range,
all else fixed, against the true policy — the cheapest model-faithful line on a
card. Two things keep the claim honest. The mask is rebuilt at every sweep point,
because sweeping wetness or SOC crosses mask thresholds and a flip onto an action
the mask forbids there would be a lie. And the sweep walks outward from the value
the decision actually had, so the reported crossing is the nearest one — scanning
from the bottom of the range would report the floor for any decision sitting high
in it, which reads as "flips at zero laps" on a card.
"""

import numpy as np


def find_flip(policy_fn, obs, dim: int, grid, mask_fn):
    """Nearest value to the recorded state at which the policy's choice changes, or
    None if it holds across the whole range. policy_fn(obs, mask) -> action;
    mask_fn(obs) -> the head's legality at that state."""
    obs = np.asarray(obs, dtype=np.float32)
    grid = np.asarray(grid, dtype=float)
    recorded = policy_fn(obs, mask_fn(obs))
    swept = obs.copy()

    def differs(i: int) -> bool:
        swept[dim] = grid[i]
        return policy_fn(swept, mask_fn(swept)) != recorded

    start = int(np.clip(np.searchsorted(grid, float(obs[dim])), 0, len(grid) - 1))
    for offset in range(len(grid)):
        below, above = start - offset, start + offset
        for i in (below, above) if below != above else (below,):
            if 0 <= i < len(grid) and differs(i):
                return float(grid[i])
    return None
