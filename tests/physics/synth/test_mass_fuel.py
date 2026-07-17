import pytest

from senna.physics.fits.fuel import fuel_profile
from senna.physics.synth.mass_fuel import avg_fuel_load_kg, static_mass_delta_s

RACE_FUEL_KG = 70.0  # AR-10, verified 16 Jul: the 2026 allowance — never 100 kg
SC_BURN_FACTOR = 0.6
N_LAPS = 50
SC_LAPS = set(range(20, 25))  # laps 20-24 behind the safety car bend the burn line
K_M_S_PER_KG = 0.033  # a fitted joint-pace mass sensitivity, order of the F02 output


def test_total_burn_equals_allowance(make_lap_frame):
    laps = make_lap_frame(
        [
            {"track_status": "4", "is_green": False} if lap in SC_LAPS else {}
            for lap in range(1, N_LAPS + 1)
        ]
    )

    profile = fuel_profile(laps, race_fuel_kg=RACE_FUEL_KG, sc_burn_factor=SC_BURN_FACTOR)

    # T6/F-06: tank full at lights out, empty at the flag. 45 green laps plus
    # 5 SC laps at 0.6 weight the allowance over 48 lap-equivalents.
    kg_per_green_lap = RACE_FUEL_KG / (45.0 + 5.0 * SC_BURN_FACTOR)
    assert profile.iloc[0] == pytest.approx(RACE_FUEL_KG)
    assert profile.iloc[-1] == pytest.approx(kg_per_green_lap)  # exactly one burn left
    total_burn_kg = profile.iloc[0] - (profile.iloc[-1] - kg_per_green_lap)
    assert total_burn_kg == pytest.approx(RACE_FUEL_KG)

    avg_kg = avg_fuel_load_kg(laps, race_fuel_kg=RACE_FUEL_KG, sc_burn_factor=SC_BURN_FACTOR)

    # T3 runs the transform at the race-average load of this exact construction
    assert avg_kg == pytest.approx(float(profile.mean()))


def test_mass_delta_is_k_m_arithmetic():
    # E-10: mass reaches pace through the fitted k_m only, never a second path
    delta_s = static_mass_delta_s(
        k_m_s_per_kg=K_M_S_PER_KG, car_delta_kg=-30.0, fuel_delta_kg=-15.0
    )

    assert delta_s == pytest.approx(K_M_S_PER_KG * -45.0)
    unchanged = static_mass_delta_s(k_m_s_per_kg=K_M_S_PER_KG, car_delta_kg=0.0, fuel_delta_kg=0.0)
    assert unchanged == 0.0
