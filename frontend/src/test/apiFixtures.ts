// Canned 5.9.2 payloads plus a substring-routed fetch stub, so view tests exercise
// the exact wire shapes F10 serves without a network. Everything here is generic:
// no team, sponsor or driver marks may appear in fixtures (F-29).

export interface CarStateFixture {
  id: number;
  s_track: number;
  position: number;
  compound: string;
  tyre_age: number;
  gap_ahead_s: number | null;
  in_pit: boolean;
}

export interface LapFrameFixture {
  lap: number;
  cars: CarStateFixture[];
  agent: {
    soc_mj: number;
    harvest_mj: number;
    deploy_mj: number;
    mode: number;
    action: Record<string, unknown>;
    reward_terms: Record<string, number>;
    mask_reasons: Record<string, string>;
  };
  events: never[]; // fixtures keep events empty, so frames stay assignable to LapFrame
}

export const circuitSummaries = [
  { id: "bahrain_grand_prix", race_laps: 57, h_max_mj: 8.5, coverage: { ribbon: true, deg_fit: true } },
  { id: "monaco_grand_prix", race_laps: 78, h_max_mj: 5.0, coverage: { ribbon: true, deg_fit: true } },
  { id: "madrid_grand_prix", race_laps: 57, h_max_mj: 8.5, coverage: { ribbon: false, deg_fit: false } },
];

export const circuitDetail = {
  ...circuitSummaries[0],
  gltf_url: "/api/v1/assets/circuits/bahrain_grand_prix/ribbon.glb",
  lap_length_m: 5412,
  corners: [
    { number: 1, distance_m: 712.3, angle_deg: -246.6, x: 42.4, y: 8329.2 },
    { number: 2, distance_m: 811.8, angle_deg: -101.2, x: 820.8, y: 7879.0 },
  ],
  braking_zones: [
    { start_m: 529.3, end_m: 720.5, entry_kmh: 300, min_kmh: 66 },
    { start_m: 1334.3, end_m: 1513.5, entry_kmh: 286, min_kmh: 122 },
  ],
  xmode_sections: [{ start_m: 4130.8, end_m: 4703.4, length_m: 572.6 }],
  flags: {
    elevation: "stylised",
    banking: "stylised",
    source: "smoothed_z_exaggerated",
    xmode: "stylised",
  },
};

export const circuitDetailMonaco = {
  ...circuitDetail,
  ...circuitSummaries[1],
  gltf_url: "/api/v1/assets/circuits/monaco_grand_prix/ribbon.glb",
};

// a configured circuit that was never built: no ribbon, no meta, null flags
export const circuitDetailNoRibbon = {
  ...circuitSummaries[2],
  gltf_url: null,
  lap_length_m: null,
  corners: null,
  braking_zones: null,
  xmode_sections: null,
  flags: null,
};

export const simulationResult = {
  run_id: 7,
  status: "complete",
  model_version: "test-model",
  env_config_hash: "envhash-2026-a1",
  circuit_id: "bahrain_grand_prix",
  era: "2026",
  seed: 42,
  config: { grid_position: 8 },
  summary: { nominal_lap_s: 90.0 },
  created_at: "2026-07-22T10:00:00Z",
  started_at: "2026-07-22T10:00:01Z",
  finished_at: "2026-07-22T10:00:05Z",
};

// A deploy-heavy ledger for run 7: several laps deploy well past 4 MJ (the car
// harvests mid-lap, so this is legal — F-02), yet SOC never leaves [0, usable].
// Lap 4 is a pit lap (pit != 0). Every harvest stays under the 8.5 MJ cap line.
export const energyProfile = {
  run_id: 7,
  circuit_id: "bahrain_grand_prix",
  h_max_mj: 8.5,
  usable_soc_mj: 4.0,
  // a valid ledger from a 2.0 MJ start: soc = clip(prev + harvest - deploy, 0, 4).
  // Lap 5 harvests past the ceiling and clips to 4.0 — realistic, not a bug.
  laps: [
    { lap: 1, harvest_mj: 3.0, deploy_mj: 1.0, soc_mj: 4.0, mode: 1, pit: 0 },
    { lap: 2, harvest_mj: 2.0, deploy_mj: 5.5, soc_mj: 0.5, mode: 2, pit: 0 },
    { lap: 3, harvest_mj: 6.0, deploy_mj: 5.0, soc_mj: 1.5, mode: 2, pit: 0 },
    { lap: 4, harvest_mj: 4.5, deploy_mj: 4.8, soc_mj: 1.2, mode: 2, pit: 3 },
    { lap: 5, harvest_mj: 7.0, deploy_mj: 3.0, soc_mj: 4.0, mode: 1, pit: 0 },
    { lap: 6, harvest_mj: 2.0, deploy_mj: 5.2, soc_mj: 0.8, mode: 3, pit: 0 },
  ],
};

// One circuit's fitted surfaces spanning the three honesty states the flag must tell
// apart: a strong direct fit, a thin direct fit (low_confidence, no donors), and a
// 2026 cluster transfer (low_confidence with source_circuit donors). cliff_age is the
// served value — max_age_seen (or the 40-lap fallback) plus the 3-lap failure margin.
export const degradationCurves = [
  {
    circuit_id: "bahrain_grand_prix", era: "2024", compound: "HARD",
    a: 0.000878, b: 1.0671, low_confidence: false,
    max_age_seen: 30, n_laps: 999, source_circuit: null, cliff_age: 33,
  },
  {
    circuit_id: "bahrain_grand_prix", era: "2024", compound: "MEDIUM",
    a: 0.00075, b: 1.13, low_confidence: true,
    max_age_seen: 18, n_laps: 40, source_circuit: null, cliff_age: 21,
  },
  {
    circuit_id: "bahrain_grand_prix", era: "2026", compound: "HARD",
    a: 0.000414, b: 1.653, low_confidence: true,
    max_age_seen: null, n_laps: null,
    source_circuit: "australian_grand_prix,chinese_grand_prix,japanese_grand_prix,miami_grand_prix",
    cliff_age: 43,
  },
];

function lapFrames(carCount: number, laps: number): LapFrameFixture[] {
  // an affine permutation keeps positions shuffled but deterministic; 7 is coprime
  // with both grid sizes, so every rank appears exactly once
  const positionOf = (id: number) => ((id * 7 + 3) % carCount) + 1;
  const retiredId = carCount - 1;
  return Array.from({ length: laps }, (_, lapIndex) => ({
    lap: lapIndex + 1,
    cars: Array.from({ length: carCount }, (_, id) => ({
      id,
      // a retired car's fraction freezes server-side; everyone else drifts per lap
      s_track: id === retiredId ? 0.42 : (id * 0.045 + lapIndex * 0.11) % 1,
      position: positionOf(id),
      compound: id % 2 === 0 ? "MEDIUM" : "HARD",
      tyre_age: lapIndex + 1,
      gap_ahead_s: positionOf(id) === 1 ? null : 1.2,
      in_pit: id === 2 && lapIndex === 1,
    })),
    agent: {
      soc_mj: 2.1, // SOC stays inside [0, 4]
      harvest_mj: 3.2,
      deploy_mj: 3.0,
      mode: 1,
      action: { pit: 0, mode: 1 },
      reward_terms: { pace: 0.1, position: 0.0 },
      mask_reasons: {},
    },
    events: [],
  }));
}

export const lapFrames22 = lapFrames(22, 3);
export const lapFrames20 = lapFrames(20, 3); // an era-2024 run: the grid is smaller

/** A 22-car live stream: one frame per lap 1..laps, for driving the fake socket. */
export function liveStreamFrames(laps: number): LapFrameFixture[] {
  return lapFrames(22, laps);
}

// The exact dict senna/explain/cards.py build_card emits (A-03, 5.8.3): a pit-lap
// card with flip probes, and a stay-out card without (serving.yaml flip_on_pit_only).
export interface DecisionCardFixture {
  circuit: string;
  lap: number;
  track_status: string;
  state: Record<string, number>;
  masks: { pit: boolean[]; mode: boolean[]; reasons: Record<string, string> };
  action: { pit: number; mode: number };
  decision: string;
  probs: { pit: number[]; mode: number[] };
  drivers: { pit: [string, number][]; mode: [string, number][] };
  flip: string[];
  plain_language: string;
  honesty: { fidelity: Record<string, number>; model_version: string; statement: string };
}

export const decisionCardPitLap: DecisionCardFixture = {
  circuit: "bahrain_grand_prix",
  lap: 14,
  track_status: "1",
  state: { tyre_age: 13, grip_est: 0.91, gap_ahead_s: 1.4, soc_mj: 2.1, position: 6 },
  masks: {
    pit: [true, false, true, true, false, false],
    mode: [true, true, true, true],
    reasons: { "pit.1": "no soft set left" },
  },
  action: { pit: 3, mode: 1 },
  decision: "Lap 14 - pit for Hard, run balanced (probability 0.62)",
  probs: { pit: [0.21, 0, 0.14, 0.62, 0.02, 0.01], mode: [0.2, 0.55, 0.15, 0.1] },
  drivers: {
    pit: [
      ["tyre_age", 0.42],
      ["grip_est", -0.18],
      ["gap_ahead_s", 0.11],
      ["soc_mj", 0.07],
      ["position", -0.03],
    ],
    mode: [
      ["soc_mj", 0.31],
      ["gap_ahead_s", 0.22],
      ["tyre_age", -0.12],
      ["grip_est", 0.08],
      ["position", 0.04],
    ],
  },
  flip: [
    "would stay out if tyre_age were 9 laps or fewer",
    "would pit for Medium if grip_est recovered above 0.97",
  ],
  plain_language: "Tyre age was the strongest push toward this call.",
  honesty: {
    fidelity: { pit: 0.93, mode: 0.88 },
    model_version: "test-model",
    statement:
      "Attribution of the trained policy via a 93.0%-faithful surrogate of its pit head; not a causal claim.",
  },
};

export const decisionCardStayOut: DecisionCardFixture = {
  ...decisionCardPitLap,
  lap: 15,
  action: { pit: 0, mode: 1 },
  decision: "Lap 15 - stay out, run balanced (probability 0.81)",
  probs: { pit: [0.81, 0, 0.09, 0.08, 0.01, 0.01], mode: [0.2, 0.55, 0.15, 0.1] },
  flip: [], // stay-out laps skip the flip sweep (serving.yaml flip_on_pit_only)
  plain_language: "Gap ahead s was the strongest push toward this call.",
};

/** A stay-out card stamped per lap, so a scrub test can tell lap 3's card from lap 4's. */
export function decisionCardForLap(lap: number): DecisionCardFixture {
  return {
    ...decisionCardStayOut,
    lap,
    decision: `Lap ${lap} - stay out, run balanced (probability 0.74)`,
    plain_language: `Gap ahead s was the strongest push toward staying out on lap ${lap}.`,
  };
}

/** sim:lap messages for the fake socket. Without cardFor every card is null — the
 * E-15 stream for a model version with no stored explanations. */
export function simLapMessages(
  frames: LapFrameFixture[],
  cardFor?: (lap: number) => DecisionCardFixture | null,
): { type: "sim:lap"; frame: LapFrameFixture; card: DecisionCardFixture | null }[] {
  return frames.map((frame) => ({
    type: "sim:lap" as const,
    frame,
    card: cardFor?.(frame.lap) ?? null,
  }));
}

export interface EgoStrategyFixture {
  startCompound: string;
  stops: { lap: number; compound: string }[]; // strictly increasing laps
}

// Frames with a scripted ego: divergence and delta tests need exact control of the
// ego's stop signature and race position. The rest of the field keeps the affine
// background permutation, with one rank swapped so the ego can hold any position.
export function strategyFrames(
  laps: number,
  egoPosition: number,
  strategy: EgoStrategyFixture,
  carCount = 20,
): LapFrameFixture[] {
  const basePosition = (id: number) => ((id * 7 + 3) % carCount) + 1;
  const displaced = Array.from({ length: carCount }, (_, id) => id).find(
    (id) => basePosition(id) === egoPosition,
  )!;
  const positionOf = (id: number) => {
    if (id === 0) return egoPosition;
    return id === displaced ? basePosition(0) : basePosition(id);
  };
  return Array.from({ length: laps }, (_, lapIndex) => {
    const lap = lapIndex + 1;
    const stopsSoFar = strategy.stops.filter((stop) => stop.lap <= lap);
    const lastStop = stopsSoFar[stopsSoFar.length - 1];
    return {
      lap,
      cars: Array.from({ length: carCount }, (_, id) => ({
        id,
        s_track: (id * 0.045 + lapIndex * 0.11) % 1,
        position: positionOf(id),
        compound:
          id === 0
            ? (lastStop?.compound ?? strategy.startCompound)
            : id % 2 === 0
              ? "MEDIUM"
              : "HARD",
        tyre_age: id === 0 ? (lastStop === undefined ? lap : lap - lastStop.lap + 1) : lap,
        gap_ahead_s: positionOf(id) === 1 ? null : 1.2,
        in_pit: id === 0 && strategy.stops.some((stop) => stop.lap === lap),
      })),
      agent: {
        soc_mj: 2.1,
        harvest_mj: 3.2,
        deploy_mj: 3.0,
        mode: 1,
        action: { pit: 0, mode: 1 },
        reward_terms: { pace: 0.1, position: 0.0 },
        mask_reasons: {},
      },
      events: [],
    };
  });
}

// The F-24 pair: run 41 is the frozen agent on 2024 physics, run 42 replays the
// driver's real strategy; the pairing lives in both configs so a reload recovers it.
export const counterfactualAccepted = { run_id: 41, baseline_run_id: 42 };
export const simulationAccepted = { run_id: simulationResult.run_id };

export const counterfactualAgentFrames = strategyFrames(6, 3, {
  startCompound: "MEDIUM",
  stops: [{ lap: 3, compound: "HARD" }],
});
export const counterfactualBaselineFrames = strategyFrames(6, 5, {
  startCompound: "MEDIUM",
  stops: [{ lap: 5, compound: "HARD" }],
});
// the mismatched-length case: the baseline race ends on lap 4
export const counterfactualBaselineFramesShort = strategyFrames(4, 5, {
  startCompound: "MEDIUM",
  stops: [{ lap: 5, compound: "HARD" }],
});

export const counterfactualAgentRun = {
  run_id: 41,
  status: "complete",
  model_version: "test-model",
  env_config_hash: "envhash-2026-a1",
  circuit_id: "bahrain_grand_prix",
  era: "2024",
  seed: 4242,
  config: {
    circuit_id: "bahrain_grand_prix",
    era: "2024",
    grid_position: 9,
    weather_profile: "dry",
    rival_band: "test",
    seed: 4242,
    year: 2024,
    round: 1,
    driver: "C07",
    era_matched_model: "pending-F14",
    baseline_run_id: 42,
    real_stops: [[5, "HARD"]], // list-of-pairs, the counterfactuals.py wire shape
    pairing: "event_trace",
  },
  summary: { nominal_lap_s: 92.0, era_matched_model: "pending-F14", n_cars: 20, total_laps: 6 },
  created_at: "2026-07-24T10:00:00Z",
  started_at: "2026-07-24T10:00:01Z",
  finished_at: "2026-07-24T10:00:05Z",
};

export const counterfactualBaselineRun = {
  run_id: 42,
  status: "complete",
  model_version: null, // no policy network ran, so no cards — the same honesty (E-15)
  env_config_hash: "envhash-2026-a1",
  circuit_id: "bahrain_grand_prix",
  era: "2024",
  seed: 4242,
  config: {
    circuit_id: "bahrain_grand_prix",
    era: "2024",
    agent_run_id: 41,
    policy: "real_replay",
  },
  summary: {
    nominal_lap_s: 92.0,
    snapped_stops: 1, // the A-07 honesty counter is an int (worker/jobs.py), not a list
    n_cars: 20,
    total_laps: 6,
  },
  created_at: "2026-07-24T10:00:00Z",
  started_at: "2026-07-24T10:00:01Z",
  finished_at: "2026-07-24T10:00:06Z",
};

// GET /races/{year}/{round} (api/schemas.py RaceDetail): generic C-codes only (F-29)
export const raceDetail2024 = {
  year: 2024,
  round: 1,
  event_name: "Bahrain Grand Prix",
  results: [
    { driver_abbrev: "C05", team_name: "team-03", grid_position: 1, position: 1, status: "Finished", points: 25.0 },
    { driver_abbrev: "C11", team_name: "team-06", grid_position: 3, position: 2, status: "Finished", points: 18.0 },
    { driver_abbrev: "C07", team_name: "team-04", grid_position: 9, position: 14, status: "Finished", points: 0.0 },
  ],
  laps: [
    { driver: "C07", driver_number: 7, lap_number: 1, lap_time_s: 96.2, lap_time_imputed: false, position: 9, compound: "MEDIUM", tyre_life: 1, stint: 1, pit_in_time_s: null, pit_out_time_s: null },
    { driver: "C07", driver_number: 7, lap_number: 2, lap_time_s: 95.8, lap_time_imputed: false, position: 10, compound: "MEDIUM", tyre_life: 2, stint: 1, pit_in_time_s: null, pit_out_time_s: null },
  ],
};

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json", "X-Model-Version": "test-model" },
  });
}

function framesPage(url: string, allFrames: LapFrameFixture[]): LapFrameFixture[] {
  // slice by the real from_lap/to_lap params (api/routes/simulations.py) so the
  // client's sequential page loop is exercised against the actual wire contract
  const params = new URL(url, "http://fixtures").searchParams;
  const fromLap = Number(params.get("from_lap") ?? "1");
  const toLap = Number(params.get("to_lap") ?? String(fromLap + 99));
  return allFrames.filter((frame) => frame.lap >= fromLap && frame.lap <= toLap);
}

/** Replace global fetch with fixture routing keyed by URL substring; returns the
 * teardown that restores the real fetch. Overrides win over the default routes; an
 * override key may pin a method ("POST /v1/simulations"), a bare key matches any. */
export function installFetchStub(overrides: Record<string, unknown> = {}): () => void {
  const realFetch = globalThis.fetch;
  globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = String(input);
    const method = (init?.method ?? "GET").toUpperCase();
    for (const [route, payload] of Object.entries(overrides)) {
      const spaceAt = route.indexOf(" ");
      const wantsMethod = spaceAt === -1 ? null : route.slice(0, spaceAt);
      const needle = spaceAt === -1 ? route : route.slice(spaceAt + 1);
      if (wantsMethod !== null && wantsMethod !== method) continue;
      if (!url.includes(needle)) continue;
      return url.includes("/frames")
        ? jsonResponse(framesPage(url, payload as LapFrameFixture[]))
        : jsonResponse(payload);
    }
    if (method === "POST") {
      if (url.includes("/v1/counterfactuals")) return jsonResponse(counterfactualAccepted, 202);
      if (url.includes("/v1/simulations")) return jsonResponse(simulationAccepted, 202);
      return jsonResponse({ detail: `no fixture route for POST ${url}` }, 404);
    }
    if (url.includes("/v1/simulations/41/frames")) {
      return jsonResponse(framesPage(url, counterfactualAgentFrames));
    }
    if (url.includes("/v1/simulations/42/frames")) {
      return jsonResponse(framesPage(url, counterfactualBaselineFrames));
    }
    if (url.includes("/frames")) return jsonResponse(framesPage(url, lapFrames22));
    if (url.includes("/v1/simulations/7")) return jsonResponse(simulationResult);
    if (url.includes("/v1/simulations/41")) return jsonResponse(counterfactualAgentRun);
    if (url.includes("/v1/simulations/42")) return jsonResponse(counterfactualBaselineRun);
    if (url.includes("/v1/races/")) return jsonResponse(raceDetail2024);
    if (url.includes("/v1/energy/")) return jsonResponse(energyProfile);
    // french_grand_prix has no fitted block — the 404 the honest empty state renders
    if (url.includes("/v1/tyres/french_grand_prix")) {
      return jsonResponse({ detail: "no degradation fits for 'french_grand_prix'" }, 404);
    }
    if (url.includes("/v1/tyres/")) return jsonResponse(degradationCurves);
    if (url.includes(`/v1/circuits/${circuitDetailNoRibbon.id}`)) {
      return jsonResponse(circuitDetailNoRibbon);
    }
    if (url.includes(`/v1/circuits/${circuitDetailMonaco.id}`)) {
      return jsonResponse(circuitDetailMonaco);
    }
    if (url.includes(`/v1/circuits/${circuitDetail.id}`)) return jsonResponse(circuitDetail);
    if (url.includes("/v1/circuits")) return jsonResponse(circuitSummaries);
    return jsonResponse({ detail: `no fixture route for ${url}` }, 404);
  };
  return () => {
    globalThis.fetch = realFetch;
  };
}
