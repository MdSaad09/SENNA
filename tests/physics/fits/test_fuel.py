import numpy as np
import pandas as pd
import pytest

from senna.physics.fits.fuel import fuel_profile, session_fuel

RACE_FUEL_KG = 70.0  # AR-10: grade C until verified
SC_BURN_FACTOR = 0.6  # fits.yaml sc_burn_factor (stylised)


def _interrupted_race(make_fit_laps):
    # ten laps, safety car on laps 4 and 5
    overrides = [{} for _ in range(10)]
    for sc_lap in (4, 5):
        overrides[sc_lap - 1] = {"track_status": "4", "is_green": False}
    return make_fit_laps(overrides)


def test_total_burn_across_the_race_equals_the_allowance(make_fit_laps):
    laps = _interrupted_race(make_fit_laps)

    remaining_kg = fuel_profile(
        laps, race_fuel_kg=RACE_FUEL_KG, sc_burn_factor=SC_BURN_FACTOR
    ).to_numpy()

    # T6: the profile starts at the allowance and the tank empties at the flag,
    # so the fuel at the start of the final (green) lap is exactly one green burn
    green_burn_kg = RACE_FUEL_KG / (8 + 2 * SC_BURN_FACTOR)
    assert remaining_kg[0] == pytest.approx(RACE_FUEL_KG)
    assert remaining_kg[-1] == pytest.approx(green_burn_kg)


def test_sc_laps_burn_at_the_reduced_factor(make_fit_laps):
    laps = _interrupted_race(make_fit_laps)

    remaining_kg = fuel_profile(
        laps, race_fuel_kg=RACE_FUEL_KG, sc_burn_factor=SC_BURN_FACTOR
    ).to_numpy()
    burn_kg = remaining_kg[:-1] - remaining_kg[1:]  # burn during laps 1..9

    assert burn_kg[3] == pytest.approx(SC_BURN_FACTOR * burn_kg[0])  # lap 4, under SC
    assert burn_kg[4] == pytest.approx(SC_BURN_FACTOR * burn_kg[0])  # lap 5, under SC
    assert burn_kg[1] == pytest.approx(burn_kg[0])  # green laps burn evenly


def test_profile_is_monotone_decreasing(make_fit_laps):
    laps = _interrupted_race(make_fit_laps)

    remaining_kg = fuel_profile(
        laps, race_fuel_kg=RACE_FUEL_KG, sc_burn_factor=SC_BURN_FACTOR
    ).to_numpy()

    assert np.all(np.diff(remaining_kg) < 0)


def test_session_fuel_burns_the_same_kg_per_lap_in_sprint_and_race(make_fit_laps):
    # T6: a sprint's allowance scales with its length, so its burn *slope*
    # matches the race's — the level difference is absorbed by session fixed
    # effects in the joint fit, the slope is what identification rides on
    race = make_fit_laps([{} for _ in range(10)]).assign(session_id="R")
    sprint = make_fit_laps([{} for _ in range(5)]).assign(session_id="S")
    laps = pd.concat([race, sprint], ignore_index=True)

    fuel_kg = session_fuel(laps, race_fuel_kg=RACE_FUEL_KG, sc_burn_factor=SC_BURN_FACTOR)

    race_burn = fuel_kg[0] - fuel_kg[1]
    sprint_burn = fuel_kg[10] - fuel_kg[11]
    assert sprint_burn == pytest.approx(race_burn)
    assert fuel_kg[0] == pytest.approx(RACE_FUEL_KG)
    assert fuel_kg[10] == pytest.approx(RACE_FUEL_KG / 2)  # 5 of 10 laps


def test_session_fuel_stays_aligned_to_the_input_index(make_fit_laps):
    laps = make_fit_laps([{} for _ in range(6)]).assign(session_id="R")
    shuffled = laps.sample(frac=1.0, random_state=3)

    fuel_kg = session_fuel(shuffled, race_fuel_kg=RACE_FUEL_KG, sc_burn_factor=SC_BURN_FACTOR)

    # whatever the row order, lap 1 holds the full tank
    lap_one = shuffled.index[shuffled["lap_number"] == 1][0]
    assert fuel_kg[lap_one] == pytest.approx(RACE_FUEL_KG)


def test_clean_race_profile_is_exactly_affine_in_lap_number(make_fit_laps):
    laps = make_fit_laps([{} for _ in range(10)])

    remaining_kg = fuel_profile(
        laps, race_fuel_kg=RACE_FUEL_KG, sc_burn_factor=SC_BURN_FACTOR
    ).to_numpy()

    # the degenerate case behind the E-10 identifiability divergence: with no
    # interruption, fuel is a straight line in lap_number
    burn_per_lap_kg = RACE_FUEL_KG / 10
    expected_kg = RACE_FUEL_KG - (laps["lap_number"].to_numpy() - 1) * burn_per_lap_kg
    assert remaining_kg == pytest.approx(expected_kg)
