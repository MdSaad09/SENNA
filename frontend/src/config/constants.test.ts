import { expect, test } from "vitest";

import { PALETTE } from "./palette";
import {
  ANNOTATION_LIFT_M,
  DEFAULT_GRID_POSITION,
  DIVERGENCE_FLASH_MS,
  DIVERGENCE_FLASH_TINT,
  EGO_CAR_ID,
  FPS_FLOOR,
  FPS_TARGET,
  FRAMES_PAGE_SIZE,
  GRIP_AGE_SAMPLES,
  GRIP_TEMP_SAMPLES,
  LOD_DISTANCE_M,
  MAX_DRAW_CALLS_REPLAY,
  MAX_HTML_LABELS,
  MODE_ACTION_LABELS,
  PANE_BACKGROUND,
  PIT_ACTION_LABELS,
  PLAYBACK_SPEEDS,
  PROVENANCE_LOG_CAP,
  RUN_STATUS_POLL_MS,
  TYRE_TEMP_AXIS_MAX_C,
  TYRE_TEMP_AXIS_MIN_C,
  TYRE_TEMP_GRIP_PENALTY,
  TYRE_TEMP_REF_C,
  WS_CLOSE_CODES_TERMINAL,
  WS_RECONNECT_BASE_MS,
  WS_RECONNECT_FACTOR,
  WS_RECONNECT_MAX_MS,
  WS_STATUS_OPEN,
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

test("the live-socket constants hold their sized values", () => {
  // operational — first retry no more eager than the server's own 0.5 s store poll
  expect(WS_RECONNECT_BASE_MS).toBe(500);
  expect(WS_RECONNECT_FACTOR).toBe(2); // plain doubling, at the cap in four retries
  expect(WS_RECONNECT_MAX_MS).toBe(8000); // the demo stakes itself on reconnect
  expect(WS_STATUS_OPEN).toBe(101); // HTTP 101 Switching Protocols, the WS-open status
  expect(WS_CLOSE_CODES_TERMINAL).toEqual([4404, 4500]); // mirrors api/ws.py close codes
  expect(DEFAULT_GRID_POSITION).toBe(8); // hoisted from RunPicker's midfield default
});

test("the counterfactual styling constants hold their stylised values", () => {
  expect(DIVERGENCE_FLASH_MS).toBe(900); // long enough to register at 30x
  expect(DIVERGENCE_FLASH_TINT).toBe("#f43f5e"); // rose — clashes with no team colour
  expect(PANE_BACKGROUND).toBe(PALETTE.ground); // scissored panes must clear to the page ground
});

test("the action labels mirror cards.py verbatim (A-03)", () => {
  // senna/explain/cards.py _PIT_CALLS and _MODE_CALLS, transcribed by hand — the
  // card's probability arrays arrive unlabelled and these strings are their names
  expect(PIT_ACTION_LABELS).toEqual([
    "stay out",
    "pit for Soft",
    "pit for Medium",
    "pit for Hard",
    "pit for Intermediate",
    "pit for Wet",
  ]);
  expect(MODE_ACTION_LABELS).toEqual(["conserve energy", "run balanced", "attack", "defend"]);
});

test("the tyre-surface axis and tessellation constants hold their provenance values", () => {
  // sourced — obs #32 normaliser (T - 15) / 45 spans a 15-60 C displayable range
  expect(TYRE_TEMP_AXIS_MIN_C).toBe(15);
  expect(TYRE_TEMP_AXIS_MAX_C).toBe(60);
  // stylised — mirrors configs/env.yaml track_temp_dry_c; the readout slice
  expect(TYRE_TEMP_REF_C).toBe(30);
  // stylised — understated relief; the on-view label owns the honesty
  expect(TYRE_TEMP_GRIP_PENALTY).toBeCloseTo(0.08, 9);
  // operational — one grid mesh either way, so density is a readability choice
  expect(GRIP_AGE_SAMPLES).toBe(64);
  expect(GRIP_TEMP_SAMPLES).toBe(33);
});
