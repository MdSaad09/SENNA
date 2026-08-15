// What the agent actually did with its tyres, read back out of the stored race.
//
// There is no served stint list: the frames carry one compound per car per lap
// (senna/serve/frames.py:61) and the stint is the run of laps between changes. The
// energy ledger records the same stops independently as EnergyLap.pit, so the two can be
// cross-checked — stints.test.ts does exactly that, because an off-by-one in the
// boundary lap is invisible on the timeline and wrong in the pit table.

import type { LapFrame } from "../../api/types";

export interface Stint {
  compound: string;
  startLap: number;
  endLap: number;
  laps: number;
}

export function stintsFromFrames(frames: LapFrame[], carId: number): Stint[] {
  const stints: Stint[] = [];

  for (const frame of frames) {
    const car = frame.cars.find((candidate) => candidate.id === carId);
    if (car === undefined) continue;

    const current = stints[stints.length - 1];
    if (current !== undefined && current.compound === car.compound) {
      current.endLap = frame.lap;
      current.laps = current.endLap - current.startLap + 1;
      continue;
    }
    stints.push({ compound: car.compound, startLap: frame.lap, endLap: frame.lap, laps: 1 });
  }

  return stints;
}

/** The lap each stop happened on: every stint's first lap except the one the car started
 *  the race on. Compare against the ledger's non-zero EnergyLap.pit laps. */
export function pitLapsFromStints(stints: Stint[]): number[] {
  return stints.slice(1).map((stint) => stint.startLap);
}
