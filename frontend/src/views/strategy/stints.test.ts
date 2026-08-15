import { expect, test } from "vitest";

import type { LapFrame } from "../../api/types";
import { EGO_CAR_ID } from "../../config/constants";
import { energyProfile, strategyFrames } from "../../test/apiFixtures";
import { mulberry32 } from "../../test/prng";
import { pitLapsFromStints, stintsFromFrames } from "./stints";

// senna/env/scenario.py:21 COMPOUNDS, served verbatim at senna/serve/frames.py:61
const COMPOUNDS = ["SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET"];

function frameFor(lap: number, compound: string, inPit: boolean): LapFrame {
  return {
    lap,
    cars: [
      {
        id: EGO_CAR_ID,
        s_track: 0,
        position: 1,
        compound,
        tyre_age: 1,
        gap_ahead_s: null,
        in_pit: inPit,
      },
    ],
    agent: {
      soc_mj: 2.0,
      harvest_mj: 3.0,
      deploy_mj: 3.0,
      mode: 1,
      action: { pit: 0, mode: 1 },
      reward_terms: { pace: 0, position: 0, terminal: 0 },
      mask_reasons: {},
    },
    events: [],
  };
}

/** A whole race for one car: laps 1..N, compound swapping only on laps the car is in
 * the pit — the shape senna/serve/frames.py can actually produce. */
function randomRace(random: () => number): LapFrame[] {
  const totalLaps = 1 + Math.floor(random() * 60);
  let compound = COMPOUNDS[Math.floor(random() * COMPOUNDS.length)];
  const frames: LapFrame[] = [];
  for (let lap = 1; lap <= totalLaps; lap++) {
    const stops = lap > 1 && random() < 0.15;
    // a stop does NOT imply a compound change: engine.py:174 writes the pit head's
    // compound whether or not it differs, and a failure-forced pit changes nothing at
    // all. One race in seven here re-fits what it already had
    if (stops && random() >= 0.15) {
      const alternatives = COMPOUNDS.filter((option) => option !== compound);
      compound = alternatives[Math.floor(random() * alternatives.length)];
    }
    frames.push(frameFor(lap, compound, stops));
  }
  return frames;
}

test("stints partition the race with no gap, no overlap and a pit at every boundary", () => {
  // 500 races, replayable from the printed seed: an off-by-one in the boundary lap is
  // invisible by eye on the timeline but breaks the pit-schedule cross-check below
  for (let seed = 1; seed <= 500; seed++) {
    const frames = randomRace(mulberry32(seed));
    const totalLaps = frames.length;
    const stints = stintsFromFrames(frames, EGO_CAR_ID);
    const trace = `seed ${seed}`;

    expect(stints.length, trace).toBeGreaterThan(0);
    expect(stints[0].startLap, trace).toBe(1);
    expect(stints[stints.length - 1].endLap, trace).toBe(totalLaps);
    expect(
      stints.reduce((total, stint) => total + stint.laps, 0),
      trace,
    ).toBe(totalLaps);

    for (const stint of stints) {
      expect(stint.laps, trace).toBe(stint.endLap - stint.startLap + 1);
      expect(stint.laps, trace).toBeGreaterThan(0);
      expect(COMPOUNDS, trace).toContain(stint.compound);
    }

    for (let index = 1; index < stints.length; index++) {
      expect(stints[index].startLap, trace).toBe(stints[index - 1].endLap + 1);
      const boundary = frames[stints[index].startLap - 1];
      expect(boundary.cars[0].in_pit, `${trace}: lap ${boundary.lap} is not a pit lap`).toBe(true);
    }

    // and the other direction, which is the one that actually bites: every lap the car
    // was in the pit must open a stint. Splitting on compound alone silently merged a
    // same-compound stop and a failure-forced pit into the stint before them
    const boundaries = new Set(stints.slice(1).map((stint) => stint.startLap));
    for (const frame of frames.slice(1)) {
      if (!frame.cars[0].in_pit) continue;
      expect(boundaries.has(frame.lap), `${trace}: pit on lap ${frame.lap} opened no stint`).toBe(
        true,
      );
    }

    expect(pitLapsFromStints(stints), trace).toEqual(
      stints.slice(1).map((stint) => stint.startLap),
    );
  }
});

test("a two-stop race reads as three stints on the compounds it ran", () => {
  const frames = [
    frameFor(1, "SOFT", false),
    frameFor(2, "SOFT", false),
    frameFor(3, "MEDIUM", true),
    frameFor(4, "MEDIUM", false),
    frameFor(5, "MEDIUM", false),
    frameFor(6, "HARD", true),
    frameFor(7, "HARD", false),
  ];
  expect(stintsFromFrames(frames, EGO_CAR_ID)).toEqual([
    { compound: "SOFT", startLap: 1, endLap: 2, laps: 2 },
    { compound: "MEDIUM", startLap: 3, endLap: 5, laps: 3 },
    { compound: "HARD", startLap: 6, endLap: 7, laps: 2 },
  ]);
});

test("a race that never pits is one stint, and its pit schedule is empty", () => {
  const frames = [1, 2, 3].map((lap) => frameFor(lap, "HARD", false));
  const stints = stintsFromFrames(frames, EGO_CAR_ID);
  expect(stints).toHaveLength(1);
  expect(pitLapsFromStints(stints)).toEqual([]);
});

test("no frames yet means no stints, not a phantom first stint", () => {
  // a queued or just-started run: the page shows status, and this must not invent one
  expect(stintsFromFrames([], EGO_CAR_ID)).toEqual([]);
});

test("the stint boundaries agree with the same run's energy ledger", () => {
  // two independent server paths reach the browser: compound per lap in the frames
  // (serve/frames.py) and the recorded pit action in the ledger (EnergyLap.pit, 0 for
  // stayed out). They must name the same lap or one of the two views is lying
  const frames = strategyFrames(
    6,
    3,
    { startCompound: "MEDIUM", stops: [{ lap: 4, compound: "HARD" }] },
    22,
  );
  const ledgerPitLaps = energyProfile.laps.filter((lap) => lap.pit !== 0).map((lap) => lap.lap);

  expect(pitLapsFromStints(stintsFromFrames(frames, EGO_CAR_ID))).toEqual(ledgerPitLaps);
});

test("one car's stints ignore the rest of the field", () => {
  const frames = strategyFrames(
    6,
    3,
    { startCompound: "SOFT", stops: [{ lap: 3, compound: "HARD" }] },
    22,
  );
  // the background cars in this fixture never stop, so car 1 must read as one stint
  expect(stintsFromFrames(frames, 1)).toHaveLength(1);
  expect(stintsFromFrames(frames, EGO_CAR_ID)).toHaveLength(2);
});

test("a stop onto the same compound still counts as a stop", () => {
  // engine.py:174-179 — `changed` is true because the pit head is not STAY_OUT, so
  // pit_count increments, but np.where writes back the compound the car already had.
  // Nothing in masks.py forbids re-fitting the current compound
  const frames = [
    frameFor(1, "HARD", false),
    frameFor(2, "HARD", false),
    frameFor(3, "HARD", true),
    frameFor(4, "HARD", false),
  ];
  expect(stintsFromFrames(frames, EGO_CAR_ID)).toEqual([
    { compound: "HARD", startLap: 1, endLap: 2, laps: 2 },
    { compound: "HARD", startLap: 3, endLap: 4, laps: 2 },
  ]);
  expect(pitLapsFromStints(stintsFromFrames(frames, EGO_CAR_ID))).toEqual([3]);
});

test("a failure-forced pit opens a stint even though nothing was changed", () => {
  // the tyre failed: `changed` is false and the compound is untouched, but
  // pit_count += (changed | failed) still fires, so the frame ships in_pit
  const frames = [
    frameFor(1, "SOFT", false),
    frameFor(2, "SOFT", true),
    frameFor(3, "SOFT", false),
  ];
  expect(stintsFromFrames(frames, EGO_CAR_ID)).toHaveLength(2);
});
