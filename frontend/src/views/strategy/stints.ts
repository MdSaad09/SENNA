// What the agent actually did with its tyres, read back out of the stored race.
//
// There is no served stint list, so it is derived from the frames — but from `in_pit`,
// not from the compound changing. The two are not the same signal, and the difference
// loses real stops:
//
//   - a stop onto the compound already fitted. `changed = pit != STAY_OUT` is true and
//     pit_count increments, but `np.where(changed, pit, compound)` writes the value it
//     already held (senna/env/engine.py:174-179). Nothing masks that call.
//   - a forced pit after a tyre failure: `changed` is false, `failed` is true, so the
//     compound is untouched and pit_count still increments.
//
// `in_pit` is `pit_count > prev.pit_count` (senna/serve/frames.py:55) and so catches
// both. The energy ledger records the same stops independently as EnergyLap.pit, which
// is what the cross-check in stints.test.ts compares against — an off-by-one in the
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
    // a compound change without in_pit means the two served signals disagree; split
    // anyway, because a stint drawn in one colour over two compounds is a lie either way
    const boundary = current === undefined || car.in_pit || current.compound !== car.compound;

    if (!boundary) {
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
