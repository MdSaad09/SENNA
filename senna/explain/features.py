"""The names <-> indices contract for the 32-dim observation (5.5.1), owned by the
explainability layer: SHAP output is a vector of 32 numbers, and this module is what
lets a decision card call them by name. Order mirrors observation.encode exactly; the
perturbation test in tests/explain pins the mapping against drift.
"""

FEATURE_NAMES = (
    "lap_progress",                    # 0  lap / total_laps
    "position_frac",                   # 1  (position - 1) / (n_cars - 1)
    "places_gained_frac",              # 2  (grid - position) / (n_cars - 1), clipped
    "compound_is_soft",                # 3  one-hot, COMPOUNDS order (scenario.py)
    "compound_is_medium",              # 4
    "compound_is_hard",                # 5
    "compound_is_inter",               # 6
    "compound_is_wet",                 # 7
    "tyre_age_norm",                   # 8  age / tyre_age_norm_laps, capped
    "tyre_grip_est",                   # 9  the deg-fit grip estimate
    "tyre_temp_state",                 # 10 cold 0 / optimal 0.5 / past-cliff 1
    "pit_count_norm",                  # 11 stops / max_stops_norm, capped
    "second_compound_used",            # 12 F-20 flag
    "fuel_frac",                       # 13 fuel_kg / race_fuel_kg
    "soc_frac",                        # 14 soc_mj / usable_soc_mj
    "last_lap_harvest_frac",           # 15 last harvest / h_max, capped
    "last_lap_deploy_frac",            # 16 last deploy / e_dep, capped
    "gap_ahead_norm",                  # 17 min(gap, cap) / cap
    "gap_behind_norm",                 # 18
    "ahead_tyre_age_delta",            # 19 (their age - ours) / norm, clipped
    "ahead_compound_hardness_delta",   # 20 hardness step delta, clipped
    "behind_tyre_age_delta",           # 21
    "override_window",                 # 22 manual override armed (gap <= 1.0 s)
    "status_green",                    # 23 track-status one-hot (red shares green, 5.5.1)
    "status_vsc",                      # 24
    "status_sc",                       # 25
    "pit_lane_open",                   # 26
    "weather_dry",                     # 27 weather one-hot
    "weather_damp",                    # 28
    "weather_wet",                     # 29
    "wetness",                         # 30 continuous, sub-lap integrated (E-08)
    "track_temp_norm",                 # 31
)

# Dims a single-feature flip sweep makes sense for: continuous (or ordered) encodings
# only. One-hot slots and booleans are excluded — "what if compound_is_soft were 0.4"
# is not a race state. Values are the physical grid bounds of the encoded dim; the
# tri-state tyre-temp dim lists its three encoded values instead.
SWEEPABLE = {
    0: (0.0, 1.0),
    1: (0.0, 1.0),
    2: (-1.0, 1.0),
    8: (0.0, 1.0),
    9: (0.0, 1.0),
    10: (0.0, 0.5, 1.0),
    11: (0.0, 1.0),
    13: (0.0, 1.0),
    14: (0.0, 1.0),
    15: (0.0, 1.0),
    16: (0.0, 1.0),
    17: (0.0, 1.0),
    18: (0.0, 1.0),
    19: (-1.0, 1.0),
    20: (-1.0, 1.0),
    21: (-1.0, 1.0),
    30: (0.0, 1.0),
    31: (0.0, 1.0),
}


def phase_of(lap_frac: float, early: float, late: float) -> str:
    """Race phase for the background stratification (5.8.2)."""
    if lap_frac < early:
        return "early"
    if lap_frac > late:
        return "late"
    return "mid"


def physical_note(dim: int, value: float, scenario) -> str:
    """The card's translation of a normalised flip value back into race units — the
    "i.e. about 17 laps" clause of 5.8.2. Dims that are already dimensionless
    (position, grip, wetness, hardness steps) get none; a fabricated unit would read
    as precision the encoding does not carry."""
    obs_cfg = scenario.env["obs"]
    age_norm = obs_cfg["tyre_age_norm_laps"]
    if dim == 0:
        return f"about lap {value * scenario.total_laps:.0f}"
    if dim == 8:
        return f"about {value * age_norm:.0f} laps old"
    if dim in (19, 21):
        # a signed delta: dropping the sign would report a rival 17 laps fresher as
        # 17 laps older, inverting the reason for the call
        laps = value * age_norm
        return f"about {abs(laps):.0f} laps {'older' if laps >= 0 else 'fresher'}"
    if dim == 11:
        return f"about {value * obs_cfg['max_stops_norm']:.0f} stops"
    if dim == 13:
        return f"about {value * scenario.race_fuel_kg:.0f} kg of fuel"
    if dim == 14:
        return f"about {value * scenario.usable_soc_mj:.1f} MJ in the store"
    if dim == 15:
        return f"about {value * scenario.h_max_mj:.1f} MJ harvested last lap"
    if dim == 16:
        return f"about {value * scenario.e_dep_mj:.1f} MJ deployed last lap"
    if dim in (17, 18):
        return f"about {value * obs_cfg['gap_norm_cap_s']:.1f} s"
    if dim == 31:
        temp_c = obs_cfg["track_temp_min_c"] + value * obs_cfg["track_temp_span_c"]
        return f"about {temp_c:.0f} C track"
    return ""
