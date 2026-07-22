"""The playback clock's pure arithmetic (E-16): 1x is one wall second per simulated
second, so the inter-frame delay is lap_time/speed for every speed 5.9.3 offers.
"""

import pytest

from api.ws import frame_delay_s
from senna import config


def test_frame_delay_is_lap_time_over_speed_for_every_offered_speed():
    speeds = config.load("serving")["playback"]["speeds"]
    assert speeds == [1, 5, 10, 30]  # the 5.9.3 client:speed set
    for speed in speeds:
        assert frame_delay_s(93.4, speed) == pytest.approx(93.4 / speed)


def test_one_x_plays_a_lap_in_its_simulated_seconds():
    # the stylised 1x definition, stated on screen in F13
    assert frame_delay_s(90.0, 1) == pytest.approx(90.0)
