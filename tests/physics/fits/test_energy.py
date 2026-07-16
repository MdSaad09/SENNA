import pandas as pd
import pytest

from senna.physics.fits.energy import lap_energy_integrals

THROTTLE_FULL_PCT = 98.0  # fits.yaml throttle_full_pct (stylised)
MASS_KG = 800.0  # car plus fuel at this lap -- arrives as an argument (F-13)


def _trace(time_s, speed_kmh, throttle_pct, brake, trace_id=None):
    n = len(time_s)
    return pd.DataFrame(
        {
            "Time": pd.to_timedelta(time_s, unit="s"),
            "Speed": speed_kmh,
            "Throttle": throttle_pct,
            "Brake": brake,
            "trace_id": trace_id if trace_id is not None else [0] * n,
        }
    )


def test_full_throttle_seconds_match_a_hand_sum_on_irregular_timestamps():
    # AR-16: real cadence wobbles around 4-5 Hz, so the deltas are deliberately uneven
    car = _trace(
        time_s=[0.0, 0.21, 0.45, 0.70, 0.92, 1.15],
        speed_kmh=[250.0] * 6,
        throttle_pct=[100.0, 100.0, 97.0, 99.0, 100.0, 100.0],
        brake=[False] * 6,
    )

    integrals = lap_energy_integrals(
        car, throttle_full_pct=THROTTLE_FULL_PCT, mass_kg=MASS_KG
    )

    # trapezoid on the >= 98% indicator over the actual deltas: each interval
    # contributes dt * (left + right) / 2
    expected_s = 0.21 * 1.0 + 0.24 * 0.5 + 0.25 * 0.5 + 0.22 * 1.0 + 0.23 * 1.0
    assert integrals.full_throttle_s == pytest.approx(expected_s)
    assert integrals.cadence_hz == pytest.approx(1 / 0.23)  # median delta is 0.23 s


def test_braking_energy_equals_delta_kinetic_energy_by_hand():
    # one brake phase from 300 to 100 km/h; speed is flat outside it so any
    # sane phase-boundary convention lands on the same delta
    car = _trace(
        time_s=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
        speed_kmh=[300.0, 300.0, 200.0, 100.0, 100.0, 100.0],
        throttle_pct=[0.0] * 6,
        brake=[False, True, True, True, False, False],
    )

    integrals = lap_energy_integrals(
        car, throttle_full_pct=THROTTLE_FULL_PCT, mass_kg=MASS_KG
    )

    expected_mj = 0.5 * MASS_KG * ((300 / 3.6) ** 2 - (100 / 3.6) ** 2) / 1e6
    assert integrals.braking_energy_mj == pytest.approx(expected_mj, rel=1e-6)
    assert integrals.full_throttle_s == pytest.approx(0.0)


def test_nothing_integrates_across_a_trace_break():
    # a 3 s dropout split upstream by split_telemetry_gaps; braking spans the
    # break, throttle is full throughout (channels are pinned independently)
    car = _trace(
        time_s=[0.0, 0.25, 0.5, 3.5, 3.75, 4.0],
        speed_kmh=[300.0, 300.0, 250.0, 150.0, 100.0, 100.0],
        throttle_pct=[100.0] * 6,
        brake=[False, True, True, True, True, False],
        trace_id=[0, 0, 0, 1, 1, 1],
    )

    integrals = lap_energy_integrals(
        car, throttle_full_pct=THROTTLE_FULL_PCT, mass_kg=MASS_KG
    )

    # 0.5 s of full throttle in each trace; the gap contributes nothing
    assert integrals.full_throttle_s == pytest.approx(1.0)
    # two separate brake phases, 300->250 and 150->100 -- integrating across
    # the break would invent the 250->150 energy lost in the dropout
    expected_mj = (
        0.5
        * MASS_KG
        * (((300 / 3.6) ** 2 - (250 / 3.6) ** 2) + ((150 / 3.6) ** 2 - (100 / 3.6) ** 2))
        / 1e6
    )
    assert integrals.braking_energy_mj == pytest.approx(expected_mj, rel=1e-6)
    assert integrals.cadence_hz == pytest.approx(4.0)
