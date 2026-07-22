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
  events: unknown[];
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

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json", "X-Model-Version": "test-model" },
  });
}

function framesPage(url: string, allFrames: LapFrameFixture[]): LapFrameFixture[] {
  // three-lap fixtures fit in one page; later pages come back empty so any
  // sequential page loop terminates
  const page = new URL(url, "http://fixtures").searchParams.get("page") ?? "0";
  return page === "0" ? allFrames : [];
}

/** Replace global fetch with fixture routing keyed by URL substring; returns the
 * teardown that restores the real fetch. Overrides win over the default routes. */
export function installFetchStub(overrides: Record<string, unknown> = {}): () => void {
  const realFetch = globalThis.fetch;
  globalThis.fetch = async (input: RequestInfo | URL): Promise<Response> => {
    const url = String(input);
    for (const [needle, payload] of Object.entries(overrides)) {
      if (url.includes(needle)) {
        return url.includes("/frames")
          ? jsonResponse(framesPage(url, payload as LapFrameFixture[]))
          : jsonResponse(payload);
      }
    }
    if (url.includes("/frames")) return jsonResponse(framesPage(url, lapFrames22));
    if (url.includes("/v1/simulations/7")) return jsonResponse(simulationResult);
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
