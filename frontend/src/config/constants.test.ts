import { expect, test } from "vitest";

import {
  ANNOTATION_LIFT_M,
  EGO_CAR_ID,
  FPS_FLOOR,
  FPS_TARGET,
  FRAMES_PAGE_SIZE,
  LOD_DISTANCE_M,
  MAX_DRAW_CALLS_REPLAY,
  MAX_HTML_LABELS,
  PLAYBACK_SPEEDS,
  PROVENANCE_LOG_CAP,
  RUN_STATUS_POLL_MS,
} from "./constants";

// Not in the plan's numbered test list: the module contract says these values are
// pinned exactly, and the 5.10.3 budget rows are test targets, not aspirations.

test("the 5.10.3 perf budget is pinned", () => {
  expect(MAX_DRAW_CALLS_REPLAY).toBe(150);
  expect(MAX_HTML_LABELS).toBe(4);
  expect(FPS_TARGET).toBe(60);
  expect(FPS_FLOOR).toBe(45);
  expect(LOD_DISTANCE_M).toBe(500);
});

test("playback and paging mirror configs/serving.yaml", () => {
  expect(PLAYBACK_SPEEDS).toEqual([1, 5, 10, 30]); // 5.9.3 client:speed set
  expect(FRAMES_PAGE_SIZE).toBe(100);
});

test("the operational defaults hold their sized values", () => {
  expect(EGO_CAR_ID).toBe(0); // F10 CarState contract: the agent's car is id 0
  expect(RUN_STATUS_POLL_MS).toBe(1000);
  expect(ANNOTATION_LIFT_M).toBeCloseTo(0.2, 9);
  expect(PROVENANCE_LOG_CAP).toBe(50);
});
