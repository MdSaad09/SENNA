// TS mirrors of the 5.9.2 Pydantic response models (api/schemas.py). Change the
// spec before changing a shape — these are transcriptions, not designs.

export interface CircuitSummary {
  id: string;
  race_laps: number;
  h_max_mj: number;
  coverage: { ribbon: boolean; deg_fit: boolean };
}

export interface CircuitCorner {
  number: number;
  distance_m: number;
  angle_deg: number;
  x: number; // decimetres, raw FastF1 — place markers by distance_m instead
  y: number;
}

export interface BrakingZone {
  start_m: number;
  end_m: number;
  entry_kmh: number;
  min_kmh: number;
}

export interface XModeSection {
  start_m: number;
  end_m: number;
  length_m: number;
}

export interface RibbonFlags {
  elevation?: string;
  banking?: string;
  source?: string;
  xmode?: string;
  camber_deg?: number;
}

export interface CircuitDetail extends CircuitSummary {
  gltf_url: string | null;
  lap_length_m: number | null;
  corners: CircuitCorner[] | null;
  braking_zones: BrakingZone[] | null;
  xmode_sections: XModeSection[] | null;
  flags: RibbonFlags | null;
}

export interface SimulationCreate {
  circuit_id: string;
  era?: "2024" | "2026";
  grid_position: number;
  weather_profile?: "dry" | "mixed" | "wet_risk";
  rival_band?: "train" | "test";
  seed?: number | null;
  model_version?: string | null;
}

export interface JobAccepted {
  run_id: number;
  // set only by POST /counterfactuals: the replay leg of the pair (additive 5.9.2
  // divergence, F13 plan)
  baseline_run_id?: number | null;
}

export interface CounterfactualCreate {
  year: number;
  round: number;
  driver: string;
  seed?: number | null; // optional so a demo deep link can pin the pair (F13 plan)
}

// A-03: the decision card exactly as senna/explain/cards.py build_card emits it
export interface DecisionCard {
  circuit: string;
  lap: number;
  track_status: string;
  state: Record<string, number>;
  masks: { pit: boolean[]; mode: boolean[]; reasons: Record<string, string> };
  action: { pit: number; mode: number };
  decision: string;
  probs: { pit: number[]; mode: number[] };
  drivers: { pit: [string, number][]; mode: [string, number][] }; // top-5 SHAP, served order
  flip: string[]; // populated on pit-call laps only (serving.yaml flip_on_pit_only)
  plain_language: string;
  honesty: { fidelity: Record<string, number>; model_version: string; statement: string };
}

export interface RaceResultRow {
  driver_abbrev: string;
  team_name: string | null;
  grid_position: number | null;
  position: number | null;
  status: string | null;
  points: number | null;
}

export interface RaceLapRow {
  driver: string;
  driver_number: number | null;
  lap_number: number;
  lap_time_s: number | null;
  lap_time_imputed: boolean;
  position: number | null;
  compound: string | null;
  tyre_life: number | null;
  stint: number | null;
  pit_in_time_s: number | null;
  pit_out_time_s: number | null;
}

export interface RaceDetail {
  year: number;
  round: number;
  event_name: string;
  results: RaceResultRow[];
  laps: RaceLapRow[];
}

export type RunStatus = "queued" | "running" | "complete" | "failed";

export interface SimulationResult {
  run_id: number;
  status: RunStatus;
  model_version: string | null;
  env_config_hash: string | null;
  circuit_id: string | null;
  era: string | null;
  seed: number | null;
  config: Record<string, unknown> | null;
  // The server types this `dict | None` (5.9.2), so the index signature stays and these
  // named keys are a transcription of what worker/jobs.py actually writes — not a shape
  // the API promises. `points` is deliberately absent: it is served RL-scaled (the FIA
  // table over points_divisor 2.5) and no view should reach for it by accident.
  summary: {
    nominal_lap_s?: number;
    final_position?: number;
    race_time_s?: number;
    total_laps?: number;
    dnf?: boolean;
    [key: string]: unknown;
  } | null;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface CarState {
  id: number;
  s_track: number; // display-only lap fraction in [0, 1) — never a distance
  position: number;
  compound: string;
  tyre_age: number;
  gap_ahead_s: number | null;
  in_pit: boolean;
}

export interface AgentState {
  soc_mj: number;
  harvest_mj: number;
  deploy_mj: number;
  mode: number;
  action: Record<string, unknown>;
  reward_terms: Record<string, number>;
  mask_reasons: Record<string, string>;
}

export interface RaceEvent {
  kind: "sc" | "vsc" | "red" | "weather" | "pit";
  car_id: number | null;
  detail: string | null;
}

export interface LapFrame {
  lap: number;
  cars: CarState[];
  agent: AgentState;
  events: RaceEvent[];
}

export interface EnergyLap {
  lap: number;
  harvest_mj: number;
  deploy_mj: number;
  soc_mj: number;
  mode: number;
  pit: number; // 0 stayed out; 1-5 pitted for compound code + 1
}

export interface EnergyProfile {
  run_id: number;
  circuit_id: string;
  h_max_mj: number; // per-event harvest cap — the bars panel ceiling, never a deploy cap
  usable_soc_mj: number; // the 4 MJ store; the SOC axis top, served not hardcoded
  laps: EnergyLap[];
}

export interface DegradationCurve {
  circuit_id: string;
  era: string;
  compound: string;
  a: number;
  b: number;
  low_confidence: boolean;
  max_age_seen: number | null;
  n_laps: number | null;
  source_circuit: string | null; // T5 donor circuits; null for a direct fit
  cliff_age: number; // the failure cliff the sim enforces
}
