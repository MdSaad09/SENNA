// react-query hooks over the 5.9.2 endpoints. Frames arrive in sequential pages
// (serving.yaml frames.page_size); the loop stops on the first short page, so a
// finished 44-78 lap race is one request and a still-writing run cannot spin.

import { useQuery } from "@tanstack/react-query";

import { FRAMES_PAGE_SIZE, RUN_STATUS_POLL_MS } from "../config/constants";
import { apiGet } from "./client";
import type {
  CircuitDetail,
  CircuitSummary,
  DegradationCurve,
  EnergyProfile,
  LapFrame,
  SimulationResult,
} from "./types";

export function useCircuits() {
  return useQuery({
    queryKey: ["circuits"],
    queryFn: () => apiGet<CircuitSummary[]>("/v1/circuits"),
  });
}

export function useCircuit(slug: string | null) {
  return useQuery({
    queryKey: ["circuit", slug],
    queryFn: () => apiGet<CircuitDetail>(`/v1/circuits/${slug}`),
    enabled: slug !== null,
  });
}

const stillRunning = (run: SimulationResult) =>
  run.status === "queued" || run.status === "running";

export function useSimulation(runId: number | null) {
  return useQuery({
    queryKey: ["simulation", runId],
    queryFn: () => apiGet<SimulationResult>(`/v1/simulations/${runId}`),
    enabled: runId !== null,
    refetchInterval: (query) =>
      query.state.data && stillRunning(query.state.data) ? RUN_STATUS_POLL_MS : false,
  });
}

export async function fetchAllFrames(runId: number): Promise<LapFrame[]> {
  const frames: LapFrame[] = [];
  for (let fromLap = 1; ; fromLap += FRAMES_PAGE_SIZE) {
    const toLap = fromLap + FRAMES_PAGE_SIZE - 1;
    const page = await apiGet<LapFrame[]>(
      `/v1/simulations/${runId}/frames?from_lap=${fromLap}&to_lap=${toLap}`,
    );
    frames.push(...page);
    if (page.length < FRAMES_PAGE_SIZE) return frames;
  }
}

export function useRunFrames(runId: number | null, runComplete: boolean) {
  return useQuery({
    queryKey: ["frames", runId],
    queryFn: () => fetchAllFrames(runId as number),
    enabled: runId !== null && runComplete,
    staleTime: Infinity, // stored frames never change for a finished run (E-16)
  });
}

export function useEnergyProfile(runId: number | null, runComplete: boolean) {
  return useQuery({
    queryKey: ["energy", runId],
    queryFn: () => apiGet<EnergyProfile>(`/v1/energy/${runId}`),
    enabled: runId !== null && runComplete,
    staleTime: Infinity, // the ledger is fixed once the run finishes (E-16)
  });
}

export function useDegradationCurves(slug: string | null) {
  return useQuery({
    queryKey: ["tyres", slug],
    queryFn: () => apiGet<DegradationCurve[]>(`/v1/tyres/${slug}`),
    enabled: slug !== null,
    retry: false, // a 404 is an honest "no fits", not a flake to retry
    staleTime: Infinity, // fitted surfaces are config, not per-run
  });
}
