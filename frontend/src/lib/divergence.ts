// The counterfactual comparison, reduced to two pure functions over the ego's rows
// of both frame streams. Divergence reads strategy — in_pit, compound, tyre age —
// never position: the panes may swap fortunes lap one without the strategies
// differing, and the flash must not fire on luck (F-24).

import type { CarState, LapFrame } from "../api/types";
import { EGO_CAR_ID } from "../config/constants";

function egoIn(frame: LapFrame, egoId: number): CarState | undefined {
  return frame.cars.find((car) => car.id === egoId);
}

export function findDivergenceLap(
  agentFrames: LapFrame[],
  baselineFrames: LapFrame[],
  egoId: number = EGO_CAR_ID,
): number | null {
  const shared = Math.min(agentFrames.length, baselineFrames.length);
  for (let at = 0; at < shared; at++) {
    const agent = egoIn(agentFrames[at], egoId);
    const baseline = egoIn(baselineFrames[at], egoId);
    if (agent === undefined || baseline === undefined) continue;
    if (
      agent.in_pit !== baseline.in_pit ||
      agent.compound !== baseline.compound ||
      agent.tyre_age !== baseline.tyre_age
    ) {
      return agentFrames[at].lap;
    }
  }
  return null;
}

export interface DeltaPoint {
  lap: number;
  delta: number; // baseline position minus agent position: positive = agent ahead
}

export function deltaSeries(
  agentFrames: LapFrame[],
  baselineFrames: LapFrame[],
  egoId: number = EGO_CAR_ID,
): DeltaPoint[] {
  // truncated to the shared range — beyond the shorter run the comparison is undefined
  const shared = Math.min(agentFrames.length, baselineFrames.length);
  const series: DeltaPoint[] = [];
  for (let at = 0; at < shared; at++) {
    const agent = egoIn(agentFrames[at], egoId);
    const baseline = egoIn(baselineFrames[at], egoId);
    if (agent === undefined || baseline === undefined) continue;
    series.push({ lap: agentFrames[at].lap, delta: baseline.position - agent.position });
  }
  return series;
}
