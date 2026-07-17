import pandas as pd
import pytest

from senna.physics.synth.montecarlo import plan_stints, sample_races

SEED = 20260717  # synth.yaml montecarlo.seed
N_CARS = 22  # the 2026 grid: 22 cars, 11 teams (F-08) — never 20
N_LAPS = 50
FAST_N_RACES = 5  # enough to pin determinism while the default suite stays fast
FULL_N_RACES = 200  # synth.yaml montecarlo.n_races, the KS-stable draw
STINT_JITTER_SIGMA = 1.5
PIT_LOSS_MEAN_S = 21.0

COLUMNS = ["race", "car", "lap_number", "lap_time_s", "compound", "tyre_age", "is_green", "pit"]


def _race_spec() -> dict:
    return {
        "n_laps": N_LAPS,
        "t0_s": 90.0,
        "sigma_driver_s": 0.3,
        "sigma_lap_s": 0.12,
        "k_m_s_per_kg": 0.033,
        "race_fuel_kg": 70.0,  # AR-10
        "sc_burn_factor": 0.6,
        "evolution_s_per_lap": -0.04,
        "degradation": {
            "SOFT": {"a": 0.08, "b": 0.002, "offset_s": -0.6},
            "MEDIUM": {"a": 0.05, "b": 0.001, "offset_s": 0.0},
            "HARD": {"a": 0.03, "b": 0.0005, "offset_s": 0.5},
        },
        "hazards": {"sc_lambda_per_lap": 0.005, "vsc_lambda_per_lap": 0.01},
        "status_mult": {"sc": 1.4, "vsc": 1.2},
        "pit_loss_mean_s": PIT_LOSS_MEAN_S,
        "pit_loss_sigma_s": 0.8,
    }


def _draw(n_races: int, seed: int) -> pd.DataFrame:
    return sample_races(
        _race_spec(),
        n_races=n_races,
        n_cars=N_CARS,
        seed=seed,
        stint_jitter_laps_sigma=STINT_JITTER_SIGMA,
    )


def test_same_seed_byte_identical():
    first = _draw(FAST_N_RACES, SEED)
    second = _draw(FAST_N_RACES, SEED)

    # 5.5.5 discipline at generator level: everything hangs off the passed seed,
    # so two calls in the same process cannot drift apart via module state
    pd.testing.assert_frame_equal(first, second, check_exact=True)
    assert list(first.columns) == COLUMNS
    assert len(first) == FAST_N_RACES * N_CARS * N_LAPS


def test_different_seed_differs():
    first = _draw(FAST_N_RACES, SEED)
    other = _draw(FAST_N_RACES, SEED + 1)

    assert not first["lap_time_s"].equals(other["lap_time_s"])


def test_higher_deg_shortens_stints():
    gentle = _race_spec()["degradation"]
    harsh = {compound: {**terms, "a": terms["a"] * 2.0} for compound, terms in gentle.items()}

    base_plan = plan_stints(N_LAPS, gentle, pit_loss_mean_s=PIT_LOSS_MEAN_S)
    harsh_plan = plan_stints(N_LAPS, harsh, pit_loss_mean_s=PIT_LOSS_MEAN_S)

    for plan in (base_plan, harsh_plan):
        assert sum(stint_laps for _, stint_laps in plan) == N_LAPS
        assert len({compound for compound, _ in plan}) >= 2  # the two-compound rule
        assert len(plan) in (2, 3)  # 1- or 2-stop, per the plan's search space

    # doubling wear must either shorten the opening stint or buy another stop
    assert harsh_plan[0][1] < base_plan[0][1] or len(harsh_plan) > len(base_plan)


@pytest.mark.slow
def test_full_size_draw_same_seed_byte_identical():
    draw = _draw(FULL_N_RACES, SEED)
    again = _draw(FULL_N_RACES, SEED)

    pd.testing.assert_frame_equal(draw, again, check_exact=True)
    assert draw["race"].nunique() == FULL_N_RACES
    assert len(draw) == FULL_N_RACES * N_CARS * N_LAPS
