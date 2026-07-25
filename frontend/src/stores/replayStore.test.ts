import { expect, test } from "vitest";

import { PLAYBACK_SPEEDS } from "../config/constants";
import { mulberry32 } from "../test/prng";
import { advancePlayhead } from "./replayStore";

const NOMINAL_LAP_S = 90;
const MAX_LAP = 57;

test("one wall second at 5x advances five ninetieths of a lap", () => {
  const next = advancePlayhead(10, 1, 5, NOMINAL_LAP_S, MAX_LAP);
  expect(next.playheadLap).toBeCloseTo(10 + 5 / 90, 9);
  expect(next.playing).toBe(true);
});

test("doubling the speed doubles the advance", () => {
  const at5x = advancePlayhead(0, 0.5, 5, NOMINAL_LAP_S, MAX_LAP).playheadLap;
  const at10x = advancePlayhead(0, 0.5, 10, NOMINAL_LAP_S, MAX_LAP).playheadLap;
  expect(at10x).toBeCloseTo(2 * at5x, 9);
});

test("the playhead clamps at the final lap and stops playing", () => {
  const next = advancePlayhead(MAX_LAP - 0.01, 60, 30, NOMINAL_LAP_S, MAX_LAP);
  expect(next.playheadLap).toBe(MAX_LAP);
  expect(next.playing).toBe(false);
});

test("advancing from the final lap stays there, still stopped", () => {
  const next = advancePlayhead(MAX_LAP, 0.016, 1, NOMINAL_LAP_S, MAX_LAP);
  expect(next.playheadLap).toBe(MAX_LAP);
  expect(next.playing).toBe(false);
});

test("a backwards scrub can never drag the playhead negative", () => {
  const next = advancePlayhead(0.02, -10, 1, NOMINAL_LAP_S, MAX_LAP);
  expect(next.playheadLap).toBe(0);
});

// Both counterfactual panes read one playhead driven through this function, so its
// composition law IS the synced-clocks spec test at the root (F13 plan, test 13).
test("composed over random delta and speed sequences the clock is monotone, additive and clamps", () => {
  for (let trial = 0; trial < 100; trial++) {
    const seed = 7_300 + trial;
    const rng = mulberry32(seed);
    const label = `seed ${seed}`;
    const steps = 5 + Math.floor(rng() * 60);

    let playheadLap = 0;
    let playing = true;
    let summed = 0;
    for (let step = 0; step < steps && playing; step++) {
      const deltaS = rng() * 5;
      const speed = PLAYBACK_SPEEDS[Math.floor(rng() * PLAYBACK_SPEEDS.length)];
      const next = advancePlayhead(playheadLap, deltaS, speed, NOMINAL_LAP_S, MAX_LAP);
      expect(next.playheadLap, label).toBeGreaterThanOrEqual(playheadLap);
      summed += (deltaS * speed) / NOMINAL_LAP_S;
      playheadLap = next.playheadLap;
      playing = next.playing;
    }

    expect(playheadLap, label).toBeCloseTo(Math.min(MAX_LAP, summed), 9);
    if (summed >= MAX_LAP) {
      expect(playheadLap, label).toBe(MAX_LAP);
      expect(playing, label).toBe(false);
    } else {
      expect(playing, label).toBe(true);
    }
  }
});
