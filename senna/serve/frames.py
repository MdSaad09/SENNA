"""The per-lap LapFrame (5.9.2) derived from a lap-quantised RaceState. None of the
CarState fields exist directly on the env, so each is an honest derivation:

- s_track is display-only synthesis — each car's lap fraction when the leader crosses
  the line, from its gap over the circuit's fitted nominal lap time (stylised,
  configs/serving.yaml). The env holds no mid-lap position; F11 labels this
  interpolation illustrative.
- in_pit and the pit RaceEvents come from diffing pit_count against the previous
  lap's snapshot, which is why the builder is handed one.
- gap_ahead_s repeats the env's own cumulative-time arithmetic (race_env._gaps_ahead)
  so the ego's display gap is bit-identical to info["gap_ahead_s"], never a second
  derivation free to drift.

Runs once per lap in the worker — never reachable from step(), nothing pandas-shaped.
"""

from dataclasses import dataclass

import numpy as np

from senna.env.scenario import COMPOUNDS


@dataclass(frozen=True)
class LapSnapshot:
    """What the next lap's frame needs to diff against this one."""
    pit_count: np.ndarray
    track_status: str
    weather: str


def build_lap_frame(env, info: dict, prev: LapSnapshot | None) -> tuple[dict, LapSnapshot]:
    state = env._state
    n = env.n_cars
    rank = state.positions()
    by_rank = np.argsort(rank, kind="stable")

    gaps = np.empty(n)
    gaps[by_rank[0]] = np.nan  # the leader has nobody ahead
    for place in range(1, n):
        car, ahead = by_rank[place], by_rank[place - 1]
        gaps[car] = state.cumulative_time_s[car] - state.cumulative_time_s[ahead]

    # (1 - gap_to_leader / nominal) mod 1: the leader reads 0.0 fresh across the
    # line and a lapped car wraps instead of going negative
    leader_time = state.cumulative_time_s[by_rank[0]]
    to_leader = state.cumulative_time_s - leader_time
    s_track = (1.0 - to_leader / env.scenario.t0_s) % 1.0

    stopped = (state.pit_count > (prev.pit_count if prev is not None else 0))
    cars = [
        {
            "id": car,
            "s_track": float(s_track[car]),
            "position": int(rank[car]),
            "compound": COMPOUNDS[int(state.compound[car])],
            "tyre_age": int(state.tyre_age[car]),
            "gap_ahead_s": None if rank[car] == 1 else float(gaps[car]),
            "in_pit": bool(stopped[car]),
        }
        for car in range(n)
    ]

    pit_ego, mode_ego = env._ego_action
    frame = {
        "lap": int(info["lap"]),
        "cars": cars,
        "agent": {
            "soc_mj": float(info["energy"]["soc_mj"]),
            "harvest_mj": float(info["energy"]["harvest_mj"]),
            "deploy_mj": float(info["energy"]["deploy_mj"]),
            "mode": int(mode_ego),
            "action": {"pit": int(pit_ego), "mode": int(mode_ego)},
            "reward_terms": {k: float(v) for k, v in info["reward_terms"].items()},
            "mask_reasons": dict(info["mask"]["reasons"]),
        },
        "events": _events(info, prev, state, stopped),
    }
    snapshot = LapSnapshot(
        pit_count=state.pit_count.copy(),
        track_status=info["track_status"],
        weather=info["events"]["weather"],
    )
    return frame, snapshot


def _events(info: dict, prev: LapSnapshot | None, state, stopped: np.ndarray) -> list[dict]:
    lap_events: list[dict] = []
    status = info["track_status"]
    if info["events"]["red_flag"]:
        lap_events.append({"kind": "red", "car_id": None, "detail": None})
    elif prev is not None and status != prev.track_status and status in ("sc", "vsc"):
        lap_events.append({"kind": status, "car_id": None, "detail": None})
    weather = info["events"]["weather"]
    if prev is not None and weather != prev.weather:
        lap_events.append({"kind": "weather", "car_id": None,
                           "detail": f"{prev.weather} -> {weather}"})
    for car in np.flatnonzero(stopped):
        lap_events.append({"kind": "pit", "car_id": int(car),
                           "detail": f"pit for {COMPOUNDS[int(state.compound[car])]}"})
    return lap_events
