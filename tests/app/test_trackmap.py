"""The loop the track map draws is a real closed curve, not four glued sketches.

The plan promises a field that visibly circulates; that dies quietly if a segment
join jumps, the loop fails to close, or the s % 1 wrap breaks on lap boundaries —
none of which a render test can see. Geometry is pinned here instead.
"""

import math

from app.trackmap import _PERIMETER, loop_point

SAMPLES = 400


def test_adjacent_samples_never_jump():
    step = _PERIMETER / SAMPLES
    points = [loop_point(i / SAMPLES) for i in range(SAMPLES + 1)]
    for (x0, y0), (x1, y1) in zip(points[:-1], points[1:], strict=True):
        assert math.hypot(x1 - x0, y1 - y0) < 2 * step, "a segment join jumped"


def test_the_loop_closes():
    x0, y0 = loop_point(0.0)
    x1, y1 = loop_point(1.0)
    assert math.hypot(x1 - x0, y1 - y0) < 1e-9


def test_lap_fractions_wrap():
    assert loop_point(1.25) == loop_point(0.25)
    assert loop_point(-0.75) == loop_point(0.25)
