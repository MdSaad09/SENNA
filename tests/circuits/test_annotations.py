import numpy as np
import pandas as pd

from senna.circuits.annotations import (
    braking_zones,
    corners_from_circuit_info,
    xmode_sections,
)


def test_braking_zone_flagged_on_50kmh_drop_within_100m():
    distance_m = np.arange(0.0, 500.0, 5.0)
    speed_kmh = np.full_like(distance_m, 300.0)
    # 300 -> 200 km/h over 80 m: a 100 km/h drop inside a 100 m window
    braking = (distance_m >= 200.0) & (distance_m <= 280.0)
    speed_kmh[braking] = np.linspace(300.0, 200.0, braking.sum())
    speed_kmh[distance_m > 280.0] = 200.0

    zones = braking_zones(distance_m, speed_kmh, drop_kmh=50.0, window_m=100.0)

    assert len(zones) == 1
    zone = zones[0]
    assert zone["entry_kmh"] > zone["min_kmh"]
    assert zone["entry_kmh"] - zone["min_kmh"] >= 50.0
    assert zone["min_kmh"] < 250.0
    assert zone["start_m"] <= 200.0 + 5.0
    assert zone["end_m"] >= 280.0 - 5.0


def test_gentle_deceleration_not_flagged():
    distance_m = np.arange(0.0, 500.0, 5.0)
    # a 30 km/h drop spread over 300 m never exceeds 50 km/h inside any 100 m window
    speed_kmh = np.linspace(300.0, 270.0, distance_m.size)

    zones = braking_zones(distance_m, speed_kmh, drop_kmh=50.0, window_m=100.0)

    assert zones == []


def test_xmode_section_is_longest_full_throttle_stretch():
    distance_m = np.arange(0.0, 1000.0, 10.0)
    throttle_pct = np.full_like(distance_m, 50.0)
    throttle_pct[(distance_m >= 100.0) & (distance_m < 200.0)] = 100.0  # ~100 m
    throttle_pct[(distance_m >= 400.0) & (distance_m < 700.0)] = 100.0  # ~300 m, the longest

    sections = xmode_sections(distance_m, throttle_pct, full_throttle_pct=99.0)

    assert len(sections) == 2
    assert sections[0]["length_m"] >= sections[1]["length_m"]
    longest = sections[0]
    assert longest["start_m"] <= 400.0
    assert longest["end_m"] >= 690.0


def test_corners_drawn_from_circuit_info():
    corners = pd.DataFrame(
        {
            "Number": [1, 2, 3],
            "Distance": [250.0, 640.0, 1120.0],
            "X": [10.0, 20.0, 30.0],
            "Y": [-5.0, -15.0, -25.0],
            "Angle": [90.0, 45.0, 120.0],
        }
    )

    drawn = corners_from_circuit_info(corners)

    assert [corner["number"] for corner in drawn] == [1, 2, 3]
    assert drawn[1]["distance_m"] == 640.0
    assert drawn[1]["angle_deg"] == 45.0
    assert drawn[1]["x"] == 20.0
    assert drawn[1]["y"] == -15.0
