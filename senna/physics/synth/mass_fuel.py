"""T3 + T6 — mass shift and fuel budget.

The 2026 car is 30 kg lighter (AR-09) and runs the ~70 kg energy-flow-limited
allowance (AR-10, verified 16 Jul). Both reach lap time through the jointly
fitted k_m and nowhere else: T1 already runs at a fixed reference fuel, so
per-lap fuel mass never enters pace a second time (E-10).
"""

from senna.physics.fits.fuel import fuel_profile


def avg_fuel_load_kg(laps, *, race_fuel_kg: float, sc_burn_factor: float) -> float:
    """Race-average fuel load — the load T3's static mass delta is evaluated at."""
    profile = fuel_profile(laps, race_fuel_kg=race_fuel_kg, sc_burn_factor=sc_burn_factor)
    return float(profile.mean())


def static_mass_delta_s(*, k_m_s_per_kg: float, car_delta_kg: float, fuel_delta_kg: float) -> float:
    """Lap-time shift from the mass change, k_m * total kg (E-10)."""
    return k_m_s_per_kg * (car_delta_kg + fuel_delta_kg)
