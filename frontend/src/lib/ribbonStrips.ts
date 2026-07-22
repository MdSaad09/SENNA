// Zone overlays (braking, X-mode, harvest) as one merged triangle strip per theme:
// a run of paired vertices lerped from the centreline toward each ribbon edge,
// floated just above the deck. A zone whose start_m exceeds its end_m crosses the
// start/finish line and is split so no triangle bridges the s = 0 seam.

import type { Centreline } from "./centreline";

export interface StripGeometry {
  positions: Float32Array;
  indices: Uint32Array;
}

export interface StripZone {
  start_m: number;
  end_m: number;
}

interface StripOptions {
  lift_m: number;
  width_fraction: number;
}

function runSamples(centreline: Centreline, from_m: number, to_m: number): number[] {
  const samples = [from_m];
  for (let station = 0; station < centreline.stations; station++) {
    const s = centreline.cumS[station];
    if (s > from_m && s < to_m) samples.push(s);
  }
  samples.push(to_m);
  return samples;
}

export function buildStrip(
  centreline: Centreline,
  zones: StripZone[],
  { lift_m, width_fraction }: StripOptions,
): StripGeometry {
  const positions: number[] = [];
  const indices: number[] = [];

  const runs = zones.flatMap(({ start_m, end_m }) =>
    start_m <= end_m
      ? [[start_m, end_m]]
      : [
          [start_m, centreline.total],
          [0, end_m],
        ],
  );

  for (const [from_m, to_m] of runs) {
    const samples = runSamples(centreline, from_m, to_m);
    const base = positions.length / 3;

    for (const s of samples) {
      const centre = centreline.sampleAt(s);
      for (const edge of [centreline.leftAt(s), centreline.rightAt(s)]) {
        positions.push(
          centre[0] + width_fraction * (edge[0] - centre[0]),
          centre[1] + width_fraction * (edge[1] - centre[1]),
          centre[2] + width_fraction * (edge[2] - centre[2]) + lift_m,
        );
      }
    }
    for (let pair = 0; pair < samples.length - 1; pair++) {
      const left = base + pair * 2;
      indices.push(left, left + 1, left + 2, left + 1, left + 3, left + 2);
    }
  }

  return { positions: new Float32Array(positions), indices: new Uint32Array(indices) };
}
