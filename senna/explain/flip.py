"""Counterfactual flip probes (5.8.2): one feature swept across its physical range,
all else fixed, against the true policy — the cheapest model-faithful line on a
card. The mask is rebuilt at every sweep point: sweeping wetness or SOC crosses
mask thresholds, and a flip onto an action the mask forbids there would be a lie.
"""

import numpy as np


def find_flip(policy_fn, obs, dim: int, grid, mask_fn):
    """First grid value where the policy's choice departs from its choice at the
    recorded state, or None if it never does. policy_fn(obs, mask) -> action;
    mask_fn(obs) -> the head's legality at that state."""
    obs = np.asarray(obs, dtype=np.float32)
    recorded = policy_fn(obs, mask_fn(obs))
    swept = obs.copy()
    for value in grid:
        swept[dim] = value
        if policy_fn(swept, mask_fn(swept)) != recorded:
            return float(value)
    return None
