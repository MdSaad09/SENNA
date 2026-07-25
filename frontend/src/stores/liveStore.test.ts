import { beforeEach, expect, test } from "vitest";

import type { LapFrame } from "../api/types";
import { mulberry32 } from "../test/prng";
import { insertFrame, useLiveStore } from "./liveStore";

const NOMINAL_LAP_S = 90;

function frameFor(lap: number): LapFrame {
  return {
    lap,
    cars: [],
    agent: {
      soc_mj: 2.0,
      harvest_mj: 3.0,
      deploy_mj: 2.8,
      mode: 1,
      action: { pit: 0, mode: 1 },
      reward_terms: {},
      mask_reasons: {},
    },
    events: [],
  };
}

function receiveLaps(from: number, to: number) {
  for (let lap = from; lap <= to; lap++) {
    useLiveStore.getState().receiveLap(frameFor(lap), null);
  }
}

beforeEach(() => {
  useLiveStore.getState().reset();
});

test("frames arriving while following carry the playhead to the head", () => {
  receiveLaps(1, 3);
  expect(useLiveStore.getState().following).toBe(true);
  expect(useLiveStore.getState().playheadLap).toBe(3);
});

test("a tick at the buffer head clamps and keeps playing while the stream is filling", () => {
  receiveLaps(1, 5);
  useLiveStore.getState().setPlaying(true);
  useLiveStore.getState().tick(600, NOMINAL_LAP_S); // ten wall minutes at 1x
  const state = useLiveStore.getState();
  expect(state.playheadLap).toBe(5); // clamped at the newest buffered lap
  expect(state.playing).toBe(true); // a buffer underrun is not the end of the race
});

test("the same tick past the head stops playback once sim:complete arrived", () => {
  receiveLaps(1, 5);
  useLiveStore.getState().markComplete();
  useLiveStore.getState().setPlaying(true);
  useLiveStore.getState().tick(600, NOMINAL_LAP_S);
  const state = useLiveStore.getState();
  expect(state.playheadLap).toBe(5);
  expect(state.playing).toBe(false);
});

test("scrubbing back flips following and moves only the playhead", () => {
  receiveLaps(1, 10);
  useLiveStore.getState().setPlaying(true);
  const framesBefore = useLiveStore.getState().frames;

  useLiveStore.getState().scrubTo(3);

  const state = useLiveStore.getState();
  expect(state.playheadLap).toBe(3);
  expect(state.following).toBe(false);
  expect(state.playing).toBe(true); // a scrub repositions, it does not pause
  expect(state.frames).toBe(framesBefore); // the delivered buffer is untouched (E-16)
});

test("frames arriving after a back-scrub fill the buffer without moving the playhead", () => {
  receiveLaps(1, 5);
  useLiveStore.getState().scrubTo(2);
  receiveLaps(6, 7);
  const state = useLiveStore.getState();
  expect(state.playheadLap).toBe(2);
  expect(state.frames.map((frame) => frame.lap)).toEqual([1, 2, 3, 4, 5, 6, 7]);
});

test("playing forward onto the head rejoins the live stream", () => {
  receiveLaps(1, 5);
  useLiveStore.getState().scrubTo(2);
  expect(useLiveStore.getState().following).toBe(false);

  useLiveStore.getState().setPlaying(true);
  useLiveStore.getState().tick(600, NOMINAL_LAP_S);

  const state = useLiveStore.getState();
  expect(state.playheadLap).toBe(5);
  expect(state.following).toBe(true);
  expect(state.playing).toBe(true);
});

test("random-order inserts with duplicates always leave a sorted 1..N buffer", () => {
  for (let trial = 0; trial < 50; trial++) {
    const seed = 26_000 + trial;
    const rng = mulberry32(seed);
    const total = 1 + Math.floor(rng() * 40);
    // every lap once, a third of them again as duplicates, all shuffled together —
    // the reconnect stream in miniature (E-16's guaranteed duplicate frame)
    const laps = Array.from({ length: total }, (_, i) => i + 1);
    const order = [...laps, ...laps.filter(() => rng() < 0.34)];
    for (let i = order.length - 1; i > 0; i--) {
      const j = Math.floor(rng() * (i + 1));
      [order[i], order[j]] = [order[j], order[i]];
    }

    let frames: LapFrame[] = [];
    const seen = new Set<number>();
    for (const lap of order) {
      const next = insertFrame(frames, frameFor(lap));
      if (seen.has(lap)) {
        expect(next, `seed ${seed}: duplicate lap ${lap}`).toBe(frames);
      }
      seen.add(lap);
      frames = next;
    }
    expect(frames.map((frame) => frame.lap), `seed ${seed}`).toEqual(laps);
  }
});
