// Plain English for the 32 observation dims.
//
// SHAP hands back feature names from senna/explain/features.py — `compound_is_soft`,
// `override_window`, `last_lap_harvest_frac`. Rendered raw and truncated to fit a column
// they read as `compound_is_so…`, which is not interpretability, it is a variable dump.
// A reader who cannot parse the label cannot check the claim.
//
// stylised — the wording only. Each entry is a reading of the comment beside that dim in
// features.py, and the mapping is keyed by the served name, so a renamed or reordered
// feature falls through to its raw name rather than silently mislabelling a bar.
export const FEATURE_LABELS: Record<string, string> = {
  lap_progress: "how far into the race",
  position_frac: "track position",
  places_gained_frac: "places gained since the grid",
  compound_is_soft: "on softs",
  compound_is_medium: "on mediums",
  compound_is_hard: "on hards",
  compound_is_inter: "on intermediates",
  compound_is_wet: "on wets",
  tyre_age_norm: "tyre age",
  tyre_grip_est: "grip left",
  tyre_temp_state: "tyre temperature state",
  pit_count_norm: "stops made",
  second_compound_used: "second compound used",
  fuel_frac: "fuel remaining",
  soc_frac: "battery charge",
  last_lap_harvest_frac: "energy recovered last lap",
  last_lap_deploy_frac: "energy spent last lap",
  gap_ahead_norm: "gap to the car ahead",
  gap_behind_norm: "gap to the car behind",
  ahead_tyre_age_delta: "tyre age vs the car ahead",
  ahead_compound_hardness_delta: "compound vs the car ahead",
  behind_tyre_age_delta: "tyre age vs the car behind",
  override_window: "manual override available",
  status_green: "green flag",
  status_vsc: "virtual safety car",
  status_sc: "safety car",
  pit_lane_open: "pit lane open",
  weather_dry: "dry",
  weather_damp: "damp",
  weather_wet: "wet",
  wetness: "how wet the track is",
  track_temp_norm: "track temperature",
};

export function featureLabel(name: string): string {
  return FEATURE_LABELS[name] ?? name;
}
