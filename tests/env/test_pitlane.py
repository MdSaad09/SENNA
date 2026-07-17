"""The pit lane as a FIFO with per-car service draws (E-05). Simultaneous stops
resolve by cumulative service time, never an in-place swap, and no two cars
leave within lane_gap_s of each other — the mechanism behind double-stacking.
"""

import numpy as np

from senna.env.pitlane import resolve_pit_lane

LANE_GAP_S = 1.0


def test_equal_service_preserves_arrival_order():
    # distinct arrivals, identical stationary time: the queue never reshuffles
    arrival_s = np.arange(22, dtype=float) * 0.5
    service_s = np.full(22, 3.0)

    exit_s = resolve_pit_lane(arrival_s, service_s, lane_gap_s=LANE_GAP_S)

    assert np.array_equal(np.argsort(exit_s), np.argsort(arrival_s))
    assert np.all(np.diff(exit_s) > 0)


def test_original_car_indexing_is_preserved(rng):
    # the returned array is indexed by car, not by queue position
    arrival_s = rng.permutation(np.arange(22, dtype=float))
    service_s = np.full(22, 2.5)

    exit_s = resolve_pit_lane(arrival_s, service_s, lane_gap_s=LANE_GAP_S)

    assert np.argmin(exit_s) == np.argmin(arrival_s)
    assert np.argmax(exit_s) == np.argmax(arrival_s)


def test_bunched_arrivals_leave_at_least_a_lane_gap_apart():
    # 22 cars box on the same lap under the safety car
    arrival_s = np.zeros(22)
    service_s = np.full(22, 2.0)

    exit_s = resolve_pit_lane(arrival_s, service_s, lane_gap_s=LANE_GAP_S)

    spacing_s = np.diff(np.sort(exit_s))
    assert np.all(spacing_s >= LANE_GAP_S - 1e-9)


def test_double_stacking_loss_grows_with_queue_position():
    # a later car in the same queue waits strictly longer to clear the lane
    arrival_s = np.zeros(22)
    service_s = np.full(22, 2.0)

    exit_s = resolve_pit_lane(arrival_s, service_s, lane_gap_s=LANE_GAP_S)

    assert np.all(np.diff(exit_s) > 0)
    assert exit_s[-1] > exit_s[0]
