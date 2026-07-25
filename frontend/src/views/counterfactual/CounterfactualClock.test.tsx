import { cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { useReplayStore } from "../../stores/replayStore";
import CounterfactualClock from "./CounterfactualClock";

const NOMINAL_LAP_S = 92;
const SHARED_MAX_LAP = 6;

// Hand-cranked rAF: the test owns every timestamp the clock ever sees, so deltas
// come from consecutive pumped timestamps (the first frame is only the baseline).
let pendingFrames: Map<number, FrameRequestCallback>;
let nextHandle: number;

function pump(nowMs: number) {
  const due = [...pendingFrames.values()];
  pendingFrames.clear();
  for (const callback of due) callback(nowMs);
}

beforeEach(() => {
  pendingFrames = new Map();
  nextHandle = 1;
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
    pendingFrames.set(nextHandle, callback);
    return nextHandle++;
  });
  vi.stubGlobal("cancelAnimationFrame", (handle: number) => {
    pendingFrames.delete(handle);
  });
  useReplayStore.setState({ playing: false, speed: 1, playheadLap: 0, selectedCarId: null });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function renderClock() {
  return render(
    <CounterfactualClock nominalLapS={NOMINAL_LAP_S} sharedMaxLap={SHARED_MAX_LAP} />,
  );
}

test("the clock drives the shared store at the run's nominal lap time", () => {
  renderClock();
  useReplayStore.setState({ playing: true });
  pump(0);
  pump(460);
  pump(920);
  // 0.92 wall seconds at 1x is 0.92 / 92 of a lap
  expect(useReplayStore.getState().playheadLap).toBeCloseTo(0.92 / NOMINAL_LAP_S, 9);
});

test("a mid-run speed change changes the rate immediately", () => {
  renderClock();
  useReplayStore.setState({ playing: true });
  pump(0);
  pump(1000); // one second at 1x
  const atOneX = useReplayStore.getState().playheadLap;
  expect(atOneX).toBeCloseTo(1 / NOMINAL_LAP_S, 9);

  useReplayStore.getState().setSpeed(30);
  pump(2000); // one second at 30x
  expect(useReplayStore.getState().playheadLap).toBeCloseTo(atOneX + 30 / NOMINAL_LAP_S, 9);
});

test("a paused store does not advance", () => {
  renderClock();
  pump(0);
  pump(500);
  pump(1000);
  expect(useReplayStore.getState().playheadLap).toBe(0);
});

test("the clock clamps at the shared final lap and stops", () => {
  renderClock();
  useReplayStore.setState({ playing: true });
  pump(0);
  pump(20 * 60 * 1000); // twenty minutes: far past six laps even at 1x
  const state = useReplayStore.getState();
  expect(state.playheadLap).toBe(SHARED_MAX_LAP);
  expect(state.playing).toBe(false);
});

test("unmount cancels the rAF loop", () => {
  const { unmount } = renderClock();
  useReplayStore.setState({ playing: true });
  pump(0);
  pump(100);
  const before = useReplayStore.getState().playheadLap;

  unmount();
  expect(pendingFrames.size).toBe(0); // the pending frame was cancelled
  pump(5000); // a straggler timestamp after unmount moves nothing
  expect(useReplayStore.getState().playheadLap).toBe(before);
});
