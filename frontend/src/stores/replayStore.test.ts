import { expect, test } from "vitest";

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
