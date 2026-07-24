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
  summary: { nominal_lap_s?: number; [key: string]: unknown } | null;
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
