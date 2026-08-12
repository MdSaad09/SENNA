import numpy as np
import pytest

from senna.physics.fits.joint_pace import JointPaceFit, fit_joint_pace, pool_k_m

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


def _fit(k_m: float, se: float) -> JointPaceFit:
    """A minimal identified fit — pool_k_m reads only these four fields."""
    return JointPaceFit(
        t0_s=90.0, k_m_s_per_kg=k_m, k_m_se_s_per_kg=se, evolution_s_per_lap=-0.01,
        trend_s_per_lap=-0.02, identified=True, vif_fuel=5.0, condition_number=10.0,
        sigma_driver_s=0.5, compound_offsets_s={}, t_ref_s=90.0, s_ref_s=1.0,
        n_laps=2000, n_excluded_no_tyre_age=0,
    )


def test_a_non_positive_pooled_k_m_is_refused():
    # a heavier car cannot be faster. A negative pool is this module's documented
    # signature of a confounded fit (see pool_k_m), so it must be refused rather
    # than published — an era with no usable pool already has a fallback, and
    # borrowing a good value beats shipping an impossible one.
    assert pool_k_m([_fit(-0.0074, 0.002)]) is None
    assert pool_k_m([_fit(0.0, 0.002)]) is None


def test_a_negative_estimate_never_reaches_the_pool(make_synthetic_race):
    """The reachable half of the guard, driven through the fitter rather than a
    hand-built fit. The pool's own `pooled <= 0` branch cannot fire once identification
    requires a positive estimate, so this is what actually stops the F18 incident: the
    confounded circuit is refused entry, not filtered out at the average."""
    race = make_synthetic_race()
    laps = race.laps.copy()
    laps["lap_time_s"] = laps["lap_time_s"] - 2 * race.k_fuel_s_per_kg * race.fuel_kg

    inverted = fit_joint_pace(laps, race.fuel_kg, vif_max=SINGLE_RACE_VIF_MAX)
    healthy = _fit(0.0119, 0.001)

    assert inverted.k_m_ols_s_per_kg < 0
    assert inverted.identified is False
    # pooling the pair must be indistinguishable from pooling the healthy fit alone
    assert pool_k_m([inverted, healthy]) == pool_k_m([healthy])


def test_a_single_confounded_circuit_cannot_invert_the_era():
    # F18: refitting on the full era made one circuit identify where none had, and
    # its negative attribution became the era's whole pool — flipping the 2026 mass
    # transform's sign. One circuit crossing the VIF gate must not do that.
    confounded = [_fit(-0.0074, 0.002)]
    healthy = [_fit(0.0119, 0.001), _fit(0.0131, 0.002)]

    assert pool_k_m(confounded) is None
    assert pool_k_m(healthy) == pytest.approx(0.0121, abs=5e-4)
    # a mixed era still pools when the weighted result stays physical. Pinned rather
    # than asserted "is None or > 0", which the contract makes true either way and so
    # cannot fail: two healthy circuits outweigh the confounded one and drag the mean
    # down from 0.0121 without taking it through zero.
    assert pool_k_m(confounded + healthy) == pytest.approx(0.008883, abs=1e-6)


def test_a_negative_mass_sensitivity_is_not_an_identified_attribution(make_synthetic_race):
    """Separable is not the same as physical. The VIF gate asks whether the design can
    tell fuel from track evolution; it cannot ask whether the answer means anything, and
    a lighter-is-slower coefficient means nothing. F18: Austria passed VIF at 22.5 on the
    wider data and published a negative k_m, which then set the whole era's pool."""
    race = make_synthetic_race()
    laps = race.laps.copy()
    # invert the fuel contribution the fixture baked in: the design is untouched, so the
    # collinearity diagnostics are identical and only the sign of the answer moves
    laps["lap_time_s"] = laps["lap_time_s"] - 2 * race.k_fuel_s_per_kg * race.fuel_kg

    fit = fit_joint_pace(laps, race.fuel_kg, vif_max=SINGLE_RACE_VIF_MAX)

    assert fit.k_m_ols_s_per_kg < 0  # the raw estimate is kept for the notebook
    assert fit.identified is False   # but it is not an attribution anyone may use
    assert fit.k_m_s_per_kg is None  # so no downstream circuit inherits it
    # the trend the data does pin down survives; only the attribution is withheld
    assert fit.trend_s_per_lap is not None
    assert fit.vif_fuel < SINGLE_RACE_VIF_MAX  # the design was separable all along
