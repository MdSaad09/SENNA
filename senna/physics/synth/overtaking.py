"""T7 — overtaking model: P(pass | pace delta, override available).

Refit on 2026 rounds 1-6 overtake counts. The 2026 Manual Override is worth
far less than DRS (~0.1-0.2 s vs 0.6-0.8 s), so passing is harder than in 2024;
the fitted 2026 intercept shift carries that. An opportunity is a follower
within the detection gap at the line on a green lap (F-05); pit cycles, lap 1,
safety-car laps, restarts and passes on retiring cars are not racing evidence
and are excluded, each counted.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from senna.physics.synth.frames import FIRST_2026_SEASON, refuse_validation_rounds

EXCLUSION_REASONS = ("lap1", "non_green", "restart", "pit_cycle", "retirement")
_MAX_NEWTON_STEPS = 100
_NEWTON_TOL = 1e-9


@dataclass(frozen=True)
class PassEvents:
    events: pd.DataFrame
    n_excluded: dict[str, int]


@dataclass(frozen=True)
class OvertakeFit:
    beta_pace: float
    shift_2026: float
    n_events: int


def extract_pass_events(
    laps: pd.DataFrame,
    *,
    detection_gap_s: float,
    pace_window_laps: int,
    restart_exclude_laps: int,
    retire_lookahead_laps: int,
) -> PassEvents:
    events = []
    excluded = dict.fromkeys(EXCLUSION_REASONS, 0)
    for _, session in laps.groupby("session_id"):
        _extract_session(
            session,
            events,
            excluded,
            detection_gap_s=detection_gap_s,
            pace_window_laps=pace_window_laps,
            restart_exclude_laps=restart_exclude_laps,
            retire_lookahead_laps=retire_lookahead_laps,
        )
    columns = ["season", "round", "lap_number", "follower", "leader", "gap_s", "pace_delta_s", "passed"]
    return PassEvents(events=pd.DataFrame(events, columns=columns), n_excluded=excluded)


def _extract_session(
    session: pd.DataFrame,
    events: list,
    excluded: dict,
    *,
    detection_gap_s: float,
    pace_window_laps: int,
    restart_exclude_laps: int,
    retire_lookahead_laps: int,
) -> None:
    ordered = session.sort_values(["driver", "lap_number"])
    ordered = ordered.assign(cum_s=ordered.groupby("driver")["lap_time_s"].cumsum())
    last_lap = ordered.groupby("driver")["lap_number"].max()
    session_final_lap = int(ordered["lap_number"].max())
    restart_laps = _restart_laps(ordered, restart_exclude_laps)
    by_lap = {lap: frame for lap, frame in ordered.groupby("lap_number")}

    for lap_number, frame in by_lap.items():
        running = frame.sort_values("cum_s")
        cum = running["cum_s"].to_numpy()
        drivers = running["driver"].to_numpy()
        for rank in range(len(running) - 1):
            gap_s = float(cum[rank + 1] - cum[rank])
            if gap_s > detection_gap_s:
                continue
            leader, follower = str(drivers[rank]), str(drivers[rank + 1])
            reason = _exclusion_reason(
                lap_number, leader, follower, running,
                restart_laps=restart_laps, last_lap=last_lap,
                session_final_lap=session_final_lap,
                retire_lookahead_laps=retire_lookahead_laps,
            )
            if reason is not None:
                excluded[reason] += 1
                continue
            events.append(
                {
                    "season": int(frame["season"].iloc[0]),
                    "round": int(frame["round"].iloc[0]),
                    "lap_number": int(lap_number),
                    "follower": follower,
                    "leader": leader,
                    "gap_s": gap_s,
                    "pace_delta_s": _pace_delta_s(
                        ordered, leader, follower, lap_number, pace_window_laps
                    ),
                    "passed": _passed(by_lap.get(lap_number + 1), leader, follower),
                }
            )


def _exclusion_reason(
    lap_number, leader, follower, running, *, restart_laps, last_lap,
    session_final_lap, retire_lookahead_laps,
) -> str | None:
    if lap_number == 1:
        return "lap1"
    pair = running[running["driver"].isin([leader, follower])]
    if not bool(pair["is_green"].fillna(False).all()):
        return "non_green"
    if lap_number in restart_laps:
        return "restart"
    if _in_pit_cycle(running, lap_number, leader, follower):
        return "pit_cycle"
    leader_last = int(last_lap[leader])
    if leader_last < session_final_lap and leader_last < lap_number + retire_lookahead_laps:
        return "retirement"
    return None


def _in_pit_cycle(running: pd.DataFrame, lap_number, leader, follower) -> bool:
    pair = running[running["driver"].isin([leader, follower])]
    return bool(pair["pit_in_time_s"].notna().any() or pair["pit_out_time_s"].notna().any())


def _restart_laps(ordered: pd.DataFrame, restart_exclude_laps: int) -> set[int]:
    """Green laps within restart_exclude_laps of a preceding safety-car lap."""
    green_by_lap = ordered.groupby("lap_number")["is_green"].apply(
        lambda flags: bool(flags.fillna(False).all())
    )
    restart = set()
    remaining = 0
    for lap in sorted(green_by_lap.index):
        if not green_by_lap[lap]:
            remaining = restart_exclude_laps
        elif remaining > 0:
            restart.add(int(lap))
            remaining -= 1
    return restart


def _pace_delta_s(ordered, leader, follower, lap_number, pace_window_laps) -> float:
    """Leader minus follower recent green pace; positive when the follower is faster."""
    return _recent_pace_s(ordered, leader, lap_number, pace_window_laps) - _recent_pace_s(
        ordered, follower, lap_number, pace_window_laps
    )


def _recent_pace_s(ordered, driver, lap_number, pace_window_laps) -> float:
    history = ordered[
        (ordered["driver"] == driver)
        & (ordered["lap_number"] <= lap_number)
        & ordered["is_green"].fillna(False).astype(bool)
    ].tail(pace_window_laps)
    return float(history["lap_time_s"].median())


def _passed(next_lap: pd.DataFrame | None, leader, follower) -> bool:
    if next_lap is None:
        return False
    positions = next_lap.set_index("driver")
    if leader not in positions.index or follower not in positions.index:
        return False
    return bool(positions.loc[follower, "cum_s"] < positions.loc[leader, "cum_s"])


def fit_overtaking(events: pd.DataFrame, *, calibration_rounds: list[int]) -> OvertakeFit:
    refuse_validation_rounds(events, calibration_rounds)
    is_2026 = (events["season"] >= FIRST_2026_SEASON).to_numpy(dtype=float)
    design = np.column_stack(
        [np.ones(len(events)), events["pace_delta_s"].to_numpy(dtype=float), is_2026]
    )
    target = events["passed"].to_numpy(dtype=float)
    beta = _fit_logistic(design, target)
    return OvertakeFit(beta_pace=float(beta[1]), shift_2026=float(beta[2]), n_events=len(events))


def _fit_logistic(design: np.ndarray, target: np.ndarray) -> np.ndarray:
    """Newton-Raphson MLE — no statsmodels, the joint_pace convention."""
    beta = np.zeros(design.shape[1])
    for _ in range(_MAX_NEWTON_STEPS):
        prob = 1.0 / (1.0 + np.exp(-design @ beta))
        gradient = design.T @ (target - prob)
        weights = np.clip(prob * (1.0 - prob), 1e-9, None)
        hessian = design.T @ (weights[:, None] * design)
        step = np.linalg.solve(hessian, gradient)
        beta = beta + step
        if np.max(np.abs(step)) < _NEWTON_TOL:
            break
    return beta
