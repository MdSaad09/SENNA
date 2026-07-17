"""The pit lane as a single-file FIFO (E-05). When several cars box on the same lap
their stops do not resolve by pre-pit order — a car cannot leave until the car ahead
of it in the lane has cleared plus a minimum gap. That queueing is the mechanism
behind double-stacking losses, and it is why positions are recomputed from cumulative
race time rather than swapped in place.
"""

import numpy as np


def resolve_pit_lane(
    arrival_s: np.ndarray, service_s: np.ndarray, *, lane_gap_s: float
) -> np.ndarray:
    """Given each car's pit-entry time and its stationary service draw, return the time
    each car clears the lane, indexed by car (not by queue position).

    Cars are served in arrival order (stable, so equal arrivals keep their indexing).
    The car ahead must have cleared, plus lane_gap_s, before the next can leave — so
    bunched arrivals stack and later cars in the queue wait strictly longer."""
    order = np.argsort(arrival_s, kind="stable")
    exit_s = np.empty_like(arrival_s, dtype=float)
    prev_exit = -np.inf
    for car in order:
        start = max(arrival_s[car], prev_exit + lane_gap_s)
        exit_s[car] = start + service_s[car]
        prev_exit = exit_s[car]
    return exit_s
