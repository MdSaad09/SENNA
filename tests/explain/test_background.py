"""The background set (5.8.2). Attributions are marginal contributions against
these states, so the draw has to be honest about what it contains: an even share to
every non-empty stratum first, spare capacity filled largest-pool-first, and a
composition that reports what was actually taken. Safety-car laps are rare, and a
proportional draw would erase exactly the states the interesting pit calls live in.
"""

import numpy as np
import pytest

from senna.explain.background import stratified_background
from tests.explain.conftest import SEED


class _State:
    """Only the fields the stratifier reads: lap fraction, circuit, track status."""

    def __init__(self, circuit, lap_frac, status, tag):
        self.circuit = circuit
        self.track_status = status
        self.obs = np.full(32, float(tag), dtype=np.float32)
        self.obs[0] = lap_frac


def _pool(green_per_circuit=200, sc_per_circuit=3):
    records = []
    for circuit in ("bahrain_grand_prix", "italian_grand_prix"):
        for i in range(green_per_circuit):
            records.append(_State(circuit, (i % 10) / 10, "green", i))
        for i in range(sc_per_circuit):  # the rare stratum an even draw must protect
            records.append(_State(circuit, 0.5, "sc", 1000 + i))
    return records


def test_rare_strata_survive_the_draw():
    records = _pool()

    states, composition = stratified_background(records, 64, early=0.25, late=0.75,
                                                seed=SEED)

    assert states.shape == (64, 32)
    assert composition["size"] == 64
    assert sum(composition["strata"].values()) == 64
    # every safety-car stratum is represented: 6 sc states exist in the pool and an
    # even share takes all of them, where a proportional draw would take about one
    sc_taken = sum(n for key, n in composition["strata"].items() if key.endswith("|sc"))
    assert sc_taken == 6


def test_never_takes_more_than_a_stratum_holds():
    records = _pool(green_per_circuit=40, sc_per_circuit=2)

    _, composition = stratified_background(records, 60, early=0.25, late=0.75, seed=SEED)

    held = {}
    for record in records:
        phase = "early" if record.obs[0] < 0.25 else ("late" if record.obs[0] > 0.75 else "mid")
        key = f"{record.circuit}|{phase}|{record.track_status}"
        held[key] = held.get(key, 0) + 1
    for key, taken in composition["strata"].items():
        assert taken <= held[key], f"{key}: drew {taken} from a stratum holding {held[key]}"


def test_draw_is_deterministic():
    records = _pool()

    first, composition = stratified_background(records, 64, early=0.25, late=0.75, seed=SEED)
    again, composition_again = stratified_background(records, 64, early=0.25, late=0.75,
                                                     seed=SEED)

    assert np.array_equal(first, again)
    assert composition == composition_again


def test_refuses_a_pool_too_small_to_fill():
    records = _pool(green_per_circuit=10, sc_per_circuit=1)

    with pytest.raises(ValueError, match="cannot fill a background"):
        stratified_background(records, 1024, early=0.25, late=0.75, seed=SEED)
