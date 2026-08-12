"""The E-09 rule 5.3.4 was missing: a lap with no tyre age cannot enter a fit about
tyre age.

`tyre_life` is a regressor in the joint pace fit's own design matrix, but the clean
mask only ever asked for green, accurate, timed and unpitted. FastF1's `TyreLife` is
patchy on the older seasons — 2.1% of all 2022 laps — so 178 laps repo-wide carry a
known slick compound, pass every other rule, and have no age. They reached LAPACK as
NaN columns and killed the whole battery on the third circuit with "SVD did not
converge", which is why `configs/physics_params.yaml` could only ever be fitted on the
two seasons that happened not to contain them.

The fix is a cleaning rule, not a `nan_to_num` patch: those laps are excluded, counted
and reported like every other rule in the 5.3.4 table.
"""

import numpy as np
import pytest

from senna.physics.fits.joint_pace import age_partial_residuals, fit_joint_pace

CALIBRATION_ROUNDS = [1, 2, 3, 4, 5, 6]  # frozen split (E-14, configs/data_split.yaml)
SINGLE_RACE_VIF_MAX = 10_000.0  # one race identifies only weakly; see test_joint_pace

# every driver loses the age on this lap and keeps everything else, mirroring the
# real gaps: whole chunks of a session arrive with a compound but no TyreLife
AGELESS_LAP_NUMBER = 10


def test_laps_without_a_tyre_age_are_excluded(make_synthetic_race):
    race = make_synthetic_race()
    laps = race.laps.copy()
    ageless = laps["lap_number"] == AGELESS_LAP_NUMBER
    laps.loc[ageless, "tyre_life"] = np.nan

    fit = fit_joint_pace(
        laps,
        race.fuel_kg,
        vif_max=SINGLE_RACE_VIF_MAX,
        calibration_rounds=CALIBRATION_ROUNDS,
    )

    otherwise_clean = laps["is_green"] & laps["is_accurate"]
    assert fit.n_laps == int((otherwise_clean & ~ageless).sum())
    # lap 10 is green, accurate and mid-stint for all 20 drivers, so the tyre-age
    # rule is the only one that touches these rows
    assert fit.n_excluded_no_tyre_age == int(ageless.sum())

    # excluded, not zero-filled: a lap the regression never saw must not move the
    # coefficients it would have moved. This also catches the subtler failure of
    # dropping rows from the lap frame while the fuel series stays aligned to the
    # old mask, which leaves n_laps looking right and the attribution nonsense.
    assert fit.k_m_s_per_kg == pytest.approx(race.k_fuel_s_per_kg, rel=0.20)
    assert fit.evolution_s_per_lap == pytest.approx(race.evolution_s_per_lap, abs=0.01)


def test_the_degradation_input_drops_laps_without_a_tyre_age(make_synthetic_race):
    race = make_synthetic_race()
    laps = race.laps.copy()
    laps.loc[laps["lap_number"] == AGELESS_LAP_NUMBER, "tyre_life"] = np.nan

    residuals = age_partial_residuals(laps, race.fuel_kg, calibration_rounds=CALIBRATION_ROUNDS)

    # the power law is fitted against age, so the frame it is fitted from cannot
    # hold a row without one — same clean mask, same rule (E-09)
    assert residuals["tyre_life"].notna().all()
    assert AGELESS_LAP_NUMBER not in set(residuals["lap_number"])
    # and no NaN leaks downstream into the T5 curve fit
    assert residuals["pace_residual_s"].notna().all()


def test_a_frame_of_only_ageless_laps_raises_rather_than_fitting_nothing(make_synthetic_race):
    race = make_synthetic_race()
    laps = race.laps.assign(tyre_life=np.nan)

    with pytest.raises(ValueError) as excinfo:
        fit_joint_pace(
            laps,
            race.fuel_kg,
            vif_max=SINGLE_RACE_VIF_MAX,
            calibration_rounds=CALIBRATION_ROUNDS,
        )

    # numpy's LinAlgError is itself a ValueError, so the exception type alone
    # proves nothing here — the message has to name the rule that emptied the
    # frame, or an operator reads "SVD did not converge" and learns nothing
    assert "tyre" in str(excinfo.value).lower()
