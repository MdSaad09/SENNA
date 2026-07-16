import numpy as np
import pytest

from senna.physics.fits.joint_pace import fit_joint_pace

CALIBRATION_ROUNDS = [1, 2, 3, 4, 5, 6]  # frozen split (E-14, configs/data_split.yaml)

# One race with one SC window identifies a and b, but only weakly: fuel stays
# nearly affine in lap_number, so the fuel VIF sits in the low thousands even
# with the step. The production threshold (fits.yaml vif_max = 30) governs
# pooled per-circuit fits; here we set the bar above the single-race VIF to
# pin the estimator and the identified decision, and below it in the clean
# race to pin the flagging path.
SINGLE_RACE_VIF_MAX = 10_000.0
POOLED_VIF_MAX = 30.0


def test_recovers_injected_coefficients(make_synthetic_race):
    race = make_synthetic_race()

    fit = fit_joint_pace(
        race.laps,
        race.fuel_kg,
        vif_max=SINGLE_RACE_VIF_MAX,
        calibration_rounds=CALIBRATION_ROUNDS,
    )

    assert fit.identified is True
    assert fit.k_m_s_per_kg == pytest.approx(race.k_fuel_s_per_kg, rel=0.20)
    assert fit.evolution_s_per_lap == pytest.approx(race.evolution_s_per_lap, abs=0.01)
    # only green, accurate laps enter -- SC and in/out laps carry +35 s and
    # +20 s in the generator, so letting them through would also sink the
    # coefficient assertions above
    assert fit.n_laps == int((race.laps["is_green"] & race.laps["is_accurate"]).sum())


def test_flags_unidentifiable_clean_race(make_synthetic_race):
    race = make_synthetic_race(sc_laps=())

    fit = fit_joint_pace(
        race.laps,
        race.fuel_kg,
        vif_max=POOLED_VIF_MAX,
        calibration_rounds=CALIBRATION_ROUNDS,
    )

    # the honesty pin: with no interruption, fuel is exactly affine in
    # lap_number, so the attribution must be flagged, never invented (E-10)
    assert fit.identified is False
    assert fit.vif_fuel > POOLED_VIF_MAX
    burn_per_lap_kg = race.race_fuel_kg / race.laps["lap_number"].max()
    combined_trend = race.evolution_s_per_lap - race.k_fuel_s_per_kg * burn_per_lap_kg
    assert fit.trend_s_per_lap == pytest.approx(combined_trend, abs=0.005)


def test_compound_fixed_effects_recovered(make_synthetic_race):
    race = make_synthetic_race()

    fit = fit_joint_pace(
        race.laps,
        race.fuel_kg,
        vif_max=SINGLE_RACE_VIF_MAX,
        calibration_rounds=CALIBRATION_ROUNDS,
    )

    # assert the gap, not the levels, so the baseline normalisation stays free
    hard_vs_medium_s = fit.compound_offsets_s["HARD"] - fit.compound_offsets_s["MEDIUM"]
    assert hard_vs_medium_s == pytest.approx(race.hard_offset_s, abs=0.1)


def test_vif_and_condition_reported(make_synthetic_race):
    race = make_synthetic_race()

    fit = fit_joint_pace(
        race.laps,
        race.fuel_kg,
        vif_max=SINGLE_RACE_VIF_MAX,
        calibration_rounds=CALIBRATION_ROUNDS,
    )

    # collinearity numbers are part of the deliverable, not internal state
    assert np.isfinite(fit.vif_fuel) and fit.vif_fuel > 1.0
    assert np.isfinite(fit.condition_number) and fit.condition_number > 1.0
    assert fit.sigma_driver_s == pytest.approx(race.driver_spread_s, abs=0.08)
    assert fit.t0_s > 0.0
    assert fit.t_ref_s > 0.0
    assert fit.s_ref_s > 0.0


def test_refuses_validation_rounds(make_synthetic_race):
    race = make_synthetic_race(round_number=8)  # held out: 2026 rounds >= 7

    # E-14: the frozen split is enforced by the fitter itself, and the error
    # names the offending round
    with pytest.raises(ValueError, match=r"round.*8"):
        fit_joint_pace(
            race.laps,
            race.fuel_kg,
            vif_max=SINGLE_RACE_VIF_MAX,
            calibration_rounds=CALIBRATION_ROUNDS,
        )
