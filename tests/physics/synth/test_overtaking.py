import numpy as np
import pandas as pd
import pytest

from senna.physics.synth.overtaking import extract_pass_events, fit_overtaking

SEED = 271
CALIBRATION_ROUNDS = [1, 2, 3, 4, 5, 6]  # frozen split (E-14, configs/data_split.yaml)
DETECTION_GAP_S = 1.0  # F-05: the Manual Override window; the conftest grid scripts against it
PACE_WINDOW_LAPS = 3
RESTART_EXCLUDE_LAPS = 1
RETIRE_LOOKAHEAD_LAPS = 2

N_EVENTS = 2400
B0 = -1.0
B_PACE = 2.0
SHIFT_2026 = 1.0
PACE_SIGMA_S = 0.6
# with ~1200 events per era at these coefficients the MLE standard errors sit
# well inside a 20 percent relative band for this fixed seed
LOGISTIC_RTOL = 0.20


def test_extraction_excludes_lap1_pits_sc_restarts_retirements(make_pass_grid):
    grid = make_pass_grid()

    result = extract_pass_events(
        grid,
        detection_gap_s=DETECTION_GAP_S,
        pace_window_laps=PACE_WINDOW_LAPS,
        restart_exclude_laps=RESTART_EXCLUDE_LAPS,
        retire_lookahead_laps=RETIRE_LOOKAHEAD_LAPS,
    )
    events = result.events

    assert {
        "season",
        "round",
        "lap_number",
        "follower",
        "leader",
        "gap_s",
        "pace_delta_s",
        "passed",
    } <= set(events.columns)
    # of the seven scripted opportunities only two are legitimate racing evidence
    assert len(events) == 2

    clean_pass = events[events["lap_number"] == 3].iloc[0]
    assert clean_pass["follower"] == "ANT"
    assert clean_pass["leader"] == "BEA"
    assert bool(clean_pass["passed"]) is True
    assert clean_pass["gap_s"] == pytest.approx(0.8, abs=1e-6)

    not_taken = events[events["lap_number"] == 11].iloc[0]
    assert not_taken["follower"] == "BEA"
    assert not_taken["leader"] == "ANT"
    assert bool(not_taken["passed"]) is False
    assert not_taken["gap_s"] == pytest.approx(0.7, abs=1e-6)

    # a lap-3 pass has only two prior laps: the pace window must tolerate a
    # short history rather than drop early-race evidence
    assert events["pace_delta_s"].notna().all()

    for reason in ("lap1", "pit_cycle", "non_green", "restart", "retirement"):
        assert result.n_excluded[reason] == 1, reason


def _synthetic_events() -> pd.DataFrame:
    rng = np.random.default_rng(SEED)
    season = np.where(np.arange(N_EVENTS) % 2 == 0, 2024, 2026)
    pace_delta_s = rng.normal(0.0, PACE_SIGMA_S, N_EVENTS)
    logit = B0 + B_PACE * pace_delta_s + SHIFT_2026 * (season == 2026)
    passed = rng.uniform(size=N_EVENTS) < 1.0 / (1.0 + np.exp(-logit))
    return pd.DataFrame(
        {
            "season": season,
            "round": rng.integers(1, 7, N_EVENTS),  # calibration rounds only
            "lap_number": rng.integers(2, 55, N_EVENTS),
            "follower": "ANT",
            "leader": "BEA",
            "gap_s": rng.uniform(0.1, DETECTION_GAP_S, N_EVENTS),
            "pace_delta_s": pace_delta_s,
            "passed": passed,
        }
    )


def test_logistic_recovers_injected_shift():
    events = _synthetic_events()

    fit = fit_overtaking(events, calibration_rounds=CALIBRATION_ROUNDS)

    assert fit.n_events == N_EVENTS
    assert fit.beta_pace == pytest.approx(B_PACE, rel=LOGISTIC_RTOL)
    assert fit.shift_2026 == pytest.approx(SHIFT_2026, rel=LOGISTIC_RTOL)

    # E-14: one held-out row anywhere in the frame stops the whole fit
    poisoned = events.copy()
    poisoned.loc[poisoned.index[0], ["season", "round"]] = [2026, 9]
    with pytest.raises(ValueError, match=r"round.*9"):
        fit_overtaking(poisoned, calibration_rounds=CALIBRATION_ROUNDS)
