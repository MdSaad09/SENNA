"""Crafted synth-battery inputs: telemetry integrated from known physics and a
scripted four-car grid. Lap frames follow the tests/physics/fits/conftest.py
column contract plus `position` for T7. No network, no database anywhere.
"""

import numpy as np
import pandas as pd
import pytest

SEED = 271  # distinct from the fits conftest's 99 so cross-suite coincidences cannot hide bugs
GRAVITY_MS2 = 9.81
CADENCE_DT_RANGE_S = (0.2, 0.25)  # uneven 4-5 Hz, the real FastF1 cadence (AR-16)
SUBSTEPS_PER_SAMPLE = 50  # sub-Euler fine enough that the sampled points obey the ODE closely
TRACE_GAP_S = 5.0  # the dropout hole between trace_ids; big enough to poison a naive difference


@pytest.fixture
def make_straight_telemetry():
    """Full-throttle run (plus optional braking tail) from known physics, FastF1-native.

    Drive: m*dv/dt = 1000*p_kw/v - beta*v^2 (v in m/s). Brake: dv/dt =
    -(mu*9.81 + kappa*v^2). trace_gap_at shifts everything from that sample by
    5 s onto trace_id 1 with speeds continuing unbroken -- exactly what a
    telemetry dropout looks like after split_telemetry_gaps (AR-16).
    """

    def build(
        *,
        p_kw: float,
        beta: float,
        mass_kg: float,
        v0_kmh: float,
        n_samples: int = 120,
        brake_samples: int = 0,
        mu_brake: float = 0.0,
        kappa_brake: float = 0.0,
        trace_gap_at: int | None = None,
    ) -> pd.DataFrame:
        rng = np.random.default_rng(SEED)
        total = n_samples + brake_samples
        dt_s = rng.uniform(*CADENCE_DT_RANGE_S, size=total - 1)
        v_ms = np.empty(total)
        v_ms[0] = v0_kmh / 3.6
        for i, dt in enumerate(dt_s):
            v = v_ms[i]
            # the driver lifts at the last accel sample, so its outgoing interval brakes
            braking = i >= n_samples - 1
            for _ in range(SUBSTEPS_PER_SAMPLE):
                if braking:
                    accel = -(mu_brake * GRAVITY_MS2 + kappa_brake * v * v)
                else:
                    accel = (1000.0 * p_kw / v - beta * v * v) / mass_kg
                v += accel * dt / SUBSTEPS_PER_SAMPLE
            v_ms[i + 1] = v

        time_s = np.concatenate([[0.0], np.cumsum(dt_s)])
        trace_id = np.zeros(total, dtype=int)
        if trace_gap_at is not None:
            time_s[trace_gap_at:] += TRACE_GAP_S
            trace_id[trace_gap_at:] = 1
        return pd.DataFrame(
            {
                "Time": pd.to_timedelta(time_s, unit="s"),
                "Speed": v_ms * 3.6,
                "Throttle": np.where(np.arange(total) < n_samples, 100.0, 0.0),
                "Brake": np.arange(total) >= n_samples,
                "trace_id": trace_id,
            }
        )

    return build


def _lap_row(lap_number: int) -> dict:
    return {
        "season": 2026,
        "round": 3,
        "session_id": "2026-03-R",
        "driver": "ANT",
        "lap_number": lap_number,
        "stint": 1,
        "compound": "MEDIUM",
        "tyre_life": float(lap_number),
        "lap_time_s": 90.0,
        "track_status": "1",
        "is_accurate": True,
        "is_green": True,
        "pit_in_time_s": None,
        "pit_out_time_s": None,
        "position": 1,
    }


@pytest.fixture
def make_lap_frame():
    """One dict of overrides per lap; lap numbers run 1..n unless overridden."""

    def build(overrides_per_lap: list[dict]) -> pd.DataFrame:
        rows = [
            {**_lap_row(lap_number), **overrides}
            for lap_number, overrides in enumerate(overrides_per_lap, start=1)
        ]
        return pd.DataFrame(rows)

    return build


PASS_GRID_SC_LAP = 6  # every car runs lap 6 behind the safety car
_BASE_LAP_S = 90.0
_SC_DELAY_S = 40.0  # cumulative time lost to the SC from lap 6 on, same for the whole field

# Cumulative seconds behind a 90 s/lap metronome at each lap line. Gaps and
# next-lap swaps script exactly one T7 event of each kind:
#   L1  BEA 0.5 s behind ANT, swaps      -> excluded, lap 1
#   L3  ANT 0.8 s behind BEA, swaps      -> the clean racing pass
#   L4  DOO 0.6 s behind COL, who pits   -> excluded, pit cycle
#   L6  BEA 0.9 s behind ANT, swaps      -> excluded, non-green (SC lap)
#   L7  ANT 0.9 s behind BEA, swaps      -> excluded, restart lap
#   L9  COL 0.8 s behind DOO, who has no laps after 10 -> excluded, retirement
#   L11 BEA 0.7 s behind ANT, stays put  -> the opportunity not taken
# Every other adjacent gap is >= 2.0 s so no incidental opportunity appears.
_PASS_GRID_OFFSETS_S = {
    "ANT": [0.0, 3.0, 0.8, 0.0, 0.0, 0.0, 0.9, 0.0, 0.0, 0.0, 0.0, 0.0],
    "BEA": [0.5, 0.0, 0.0, 3.0, 3.0, 0.9, 0.0, 3.0, 3.0, 3.0, 0.7, 2.0],
    "COL": [10.0, 10.0, 10.0, 10.0, 32.0, 8.0, 8.0, 9.0, 6.8, 9.0, 4.0, 4.0],
    "DOO": [20.0, 20.0, 20.0, 10.6, 10.0, 5.0, 5.0, 6.0, 6.0, 6.0],  # retires after lap 10
}


@pytest.fixture
def make_pass_grid():
    """The scripted four-car race above as a lap frame with positions."""

    def build() -> pd.DataFrame:
        cum_s = {
            driver: [
                _BASE_LAP_S * lap + off + (_SC_DELAY_S if lap >= PASS_GRID_SC_LAP else 0.0)
                for lap, off in enumerate(offsets, start=1)
            ]
            for driver, offsets in _PASS_GRID_OFFSETS_S.items()
        }
        n_laps = max(len(times) for times in cum_s.values())
        rows = []
        for lap in range(1, n_laps + 1):
            running = sorted(
                (times[lap - 1], driver)
                for driver, times in cum_s.items()
                if len(times) >= lap
            )
            for position, (cum, driver) in enumerate(running, start=1):
                prev = cum_s[driver][lap - 2] if lap > 1 else 0.0
                stopped = driver == "COL" and lap >= 5  # COL boxes on lap 4, out on lap 5
                rows.append(
                    {
                        "season": 2026,
                        "round": 3,
                        "session_id": "2026-03-R",
                        "driver": driver,
                        "lap_number": lap,
                        "stint": 2 if stopped else 1,
                        "compound": "HARD" if stopped else "MEDIUM",
                        "tyre_life": float(lap - 4) if stopped else float(lap),
                        "lap_time_s": cum - prev,
                        "track_status": "4" if lap == PASS_GRID_SC_LAP else "1",
                        "is_accurate": not (driver == "COL" and lap in (4, 5)),
                        "is_green": lap != PASS_GRID_SC_LAP,
                        "pit_in_time_s": cum if driver == "COL" and lap == 4 else None,
                        "pit_out_time_s": cum if driver == "COL" and lap == 5 else None,
                        "position": position,
                    }
                )
        return pd.DataFrame(rows)

    return build
