"""The 1,024-state background set (5.8.2), stratified circuit x race phase x track
status. Attributions are marginal contributions *against this set*, so its
composition is documented as an artifact, not assumed. Every non-empty stratum gets
an even share first — SC and VSC laps are rare, and a proportional draw would all
but erase exactly the states the interesting pit calls live in.
"""

import numpy as np

from senna.explain.features import phase_of


def stratified_background(records, size: int, *, early: float, late: float, seed: int):
    """Returns (states (size, 32) float32, composition dict). Shortfall in thin
    strata is handed to the strata with spare states, one slot at a time, largest
    pool first — deterministic, and the composition shows what actually happened."""
    strata: dict[tuple, list[int]] = {}
    for i, record in enumerate(records):
        key = (record.circuit, phase_of(float(record.obs[0]), early, late),
               record.track_status)
        strata.setdefault(key, []).append(i)

    pool = sum(len(v) for v in strata.values())
    if pool < size:
        raise ValueError(
            f"{pool} logged states cannot fill a background of {size} — "
            "log more distillation rollouts first"
        )

    keys = sorted(strata)
    counts = {key: min(size // len(keys), len(strata[key])) for key in keys}
    while sum(counts.values()) < size:
        key = max(keys, key=lambda k: (len(strata[k]) - counts[k], k))
        counts[key] += 1

    rng = np.random.default_rng(seed)
    chosen: list[int] = []
    for key in keys:
        chosen.extend(rng.choice(strata[key], size=counts[key], replace=False).tolist())

    states = np.stack([records[i].obs for i in chosen]).astype(np.float32)
    composition = {
        "|".join(key): counts[key] for key in keys if counts[key]
    }
    return states, {"size": size, "strata": composition}
