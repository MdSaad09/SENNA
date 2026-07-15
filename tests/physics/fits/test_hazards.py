import pytest
from senna.physics.fits.hazards import (
    classify_track_status,
    status_multipliers,
    wilson_band,
)

WILSON_Z = 1.96  # fits.yaml wilson_z (sourced: 95% normal quantile)


def test_wilson_band_matches_hand_computed_values():
    # 3 SC races out of 10, z = 1.96: worked by hand from the Wilson formula
    low, high = wilson_band(3, 10, z=WILSON_Z)

    assert low == pytest.approx(0.107789, abs=1e-6)
    assert high == pytest.approx(0.603227, abs=1e-6)


def test_wilson_band_with_zero_events_keeps_a_positive_upper_bound():
    low, high = wilson_band(0, 10, z=WILSON_Z)

    # the whole point of Wilson over the normal approximation: 0/n gives a
    # usable band instead of the degenerate (0, 0)
    assert low == pytest.approx(0.0, abs=1e-12)
    assert high == pytest.approx(0.277540, abs=1e-6)


def test_track_status_digits_classify_sc_vsc_and_red():
    assert classify_track_status("1") == set()
    assert classify_track_status("2") == set()  # yellow flag: not an intervention
    assert classify_track_status("4") == {"sc"}
    assert classify_track_status("5") == {"red"}
    assert classify_track_status("6") == {"vsc"}
    assert classify_track_status("7") == {"vsc"}  # VSC ending is still VSC exposure
    # the classic trap: "12" is the digits 1 and 2, never SC
    assert classify_track_status("12") == set()
    assert classify_track_status("67") == {"vsc"}
    assert classify_track_status("45") == {"sc", "red"}


def test_status_multipliers_come_from_lap_time_medians(make_fit_laps):
    laps = make_fit_laps(
        [
            {"lap_time_s": 89.0},
            {"lap_time_s": 90.0},
            {"lap_time_s": 91.0},
            {"lap_time_s": 125.0, "track_status": "4", "is_green": False},
            {"lap_time_s": 126.0, "track_status": "4", "is_green": False},
            {"lap_time_s": 127.0, "track_status": "4", "is_green": False},
            {"lap_time_s": 116.0, "track_status": "6", "is_green": False},
            {"lap_time_s": 117.0, "track_status": "6", "is_green": False},
            {"lap_time_s": 118.0, "track_status": "7", "is_green": False},
        ]
    )

    # 5.5.3 status_mult: SC median 126 and VSC median 117 against green median 90
    multipliers = status_multipliers(laps)

    assert multipliers["sc"] == pytest.approx(1.4)
    assert multipliers["vsc"] == pytest.approx(1.3)
