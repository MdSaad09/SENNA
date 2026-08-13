"""Crafted fit-input frames in the Postgres Lap naming (senna/data/schema.py).

Column contract for laps handed to fitters: season, round, session_id, driver,
lap_number, stint, compound, tyre_life, lap_time_s, track_status, is_accurate,
is_green, pit_in_time_s, pit_out_time_s. No network, no database anywhere.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
import pytest

from senna.physics.fits.fuel import fuel_profile

RACE_LAPS = 57
N_DRIVERS = 20  # a regression sample size, not a grid — the 2026 grid is 22 (F-08)
SC_WINDOW = tuple(range(20, 25))  # laps 20-24 run behind the safety car
# chosen so a correct OLS recovers the injected coefficients well inside the
# mandated tolerances for several reasonable design matrices (age+age2 per
# compound, exact age^1.3, shared quadratic) -- verified before pinning
SEED = 99

T0_S = 92.0
K_FUEL_S_PER_KG = 0.033
EVOLUTION_S_PER_LAP = -0.04
DEG_A_S = 0.012  # A in A*age^1.3, the T5 power-law shape
DEG_EXPONENT = 1.3
HARD_OFFSET_S = 0.55
DRIVER_SPREAD_S = 0.4
LAP_NOISE_S = 0.15
RACE_FUEL_KG = 70.0  # AR-10: grade C until Saad verifies the 2026 allowance
SC_BURN_FACTOR = 0.6  # fits.yaml sc_burn_factor (stylised)
SC_DELAY_S = 35.0
IN_OUT_PENALTY_S = 20.0


def _lap_row(lap_number: int) -> dict:
    return {
        "season": 2024,
        "round": 3,
        "session_id": "2024-03-R",
        "driver": "VER",
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
    }


@pytest.fixture
def make_fit_laps():
    """One dict of overrides per lap; lap numbers run 1..n unless overridden."""

    def build(overrides_per_lap: list[dict]) -> pd.DataFrame:
        rows = [
            {**_lap_row(lap_number), **overrides}
            for lap_number, overrides in enumerate(overrides_per_lap, start=1)
        ]
        return pd.DataFrame(rows)

    return build


@dataclass(frozen=True)
class SyntheticRace:
    laps: pd.DataFrame
    fuel_kg: pd.Series  # aligned to laps.index, built by fuel_profile per driver
    k_fuel_s_per_kg: float
    evolution_s_per_lap: float
    hard_offset_s: float
    driver_spread_s: float  # sample std of the realised driver effects
    driver_effects_s: dict[str, float]  # the realised effect per driver code, uncentred
    race_fuel_kg: float
    sc_burn_factor: float


@pytest.fixture
def make_synthetic_race():
    """Seeded 57-lap, 20-driver race with known coefficients baked in.

    lap_time = t0 + driver + compound + A*age^1.3 + a*fuel + b*lap + noise.
    Fuel comes from fuel_profile, exactly as the fitter will see it: the SC
    window bends the burn line, and that step is what makes a and b jointly
    identifiable within a single race (E-10).
    """

    def build(sc_laps: tuple = SC_WINDOW, round_number: int = 3) -> SyntheticRace:
        rng = np.random.default_rng(SEED)
        under_sc = set(sc_laps)
        driver_frames = []
        fuel_columns = []
        driver_effects_s = {}

        for i in range(N_DRIVERS):
            driver_effect_s = rng.normal(0.0, DRIVER_SPREAD_S)
            driver_effects_s[f"D{i:02d}"] = driver_effect_s
            noise_s = rng.normal(0.0, LAP_NOISE_S, size=RACE_LAPS)
            pit_lap = 26 + (i % 10)  # varied stint breaks, all after the SC window
            compound_by_stint = ("HARD", "MEDIUM") if i % 2 else ("MEDIUM", "HARD")

            rows = []
            for lap in range(1, RACE_LAPS + 1):
                stint = 2 if lap > pit_lap else 1
                age = float(lap - pit_lap) if stint == 2 else float(lap)
                rows.append(
                    {
                        "season": 2026,
                        "round": round_number,
                        "session_id": f"2026-{round_number:02d}-R",
                        "driver": f"D{i:02d}",
                        "lap_number": lap,
                        "stint": stint,
                        "compound": compound_by_stint[stint - 1],
                        "tyre_life": age,
                        "track_status": "4" if lap in under_sc else "1",
                        "is_accurate": lap not in (pit_lap, pit_lap + 1),
                        "is_green": lap not in under_sc,
                        "pit_in_time_s": 90.0 * lap if lap == pit_lap else None,
                        "pit_out_time_s": 90.0 * lap if lap == pit_lap + 1 else None,
                    }
                )
            laps = pd.DataFrame(rows)
            fuel_kg = fuel_profile(
                laps, race_fuel_kg=RACE_FUEL_KG, sc_burn_factor=SC_BURN_FACTOR
            )

            lap_time_s = (
                T0_S
                + driver_effect_s
                + (laps["compound"] == "HARD") * HARD_OFFSET_S
                + DEG_A_S * laps["tyre_life"] ** DEG_EXPONENT
                + K_FUEL_S_PER_KG * fuel_kg
                + EVOLUTION_S_PER_LAP * laps["lap_number"]
                + noise_s
            )
            # SC and in/out laps are slow in reality; a fitter that lets them
            # through cannot recover the injected coefficients (E-09)
            lap_time_s = lap_time_s + ~laps["is_green"] * SC_DELAY_S
            lap_time_s = lap_time_s + ~laps["is_accurate"] * IN_OUT_PENALTY_S

            driver_frames.append(laps.assign(lap_time_s=lap_time_s))
            fuel_columns.append(fuel_kg)

        return SyntheticRace(
            laps=pd.concat(driver_frames, ignore_index=True),
            fuel_kg=pd.concat(fuel_columns, ignore_index=True),
            k_fuel_s_per_kg=K_FUEL_S_PER_KG,
            evolution_s_per_lap=EVOLUTION_S_PER_LAP,
            hard_offset_s=HARD_OFFSET_S,
            driver_spread_s=float(np.std(list(driver_effects_s.values()), ddof=1)),
            driver_effects_s=driver_effects_s,
            race_fuel_kg=RACE_FUEL_KG,
            sc_burn_factor=SC_BURN_FACTOR,
        )

    return build
