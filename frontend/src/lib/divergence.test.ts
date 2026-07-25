import { expect, test } from "vitest";

import { strategyFrames, type EgoStrategyFixture } from "../test/apiFixtures";
import { mulberry32 } from "../test/prng";
import { deltaSeries, findDivergenceLap } from "./divergence";

const oneStop = (lap: number, compound: string): EgoStrategyFixture => ({
  startCompound: "MEDIUM",
  stops: [{ lap, compound }],
});

test("a differing pit lap diverges on the earlier stop", () => {
  const agent = strategyFrames(8, 3, oneStop(3, "HARD"));
  const baseline = strategyFrames(8, 5, oneStop(5, "HARD"));
  expect(findDivergenceLap(agent, baseline)).toBe(3);
});

test("the same stop lap with a different compound still diverges there", () => {
  const agent = strategyFrames(8, 3, oneStop(4, "HARD"));
  const baseline = strategyFrames(8, 5, oneStop(4, "SOFT"));
  expect(findDivergenceLap(agent, baseline)).toBe(4);
});

test("identical strategies never diverge, whatever the positions", () => {
  // positions 3 and 5 differ every lap — divergence reads strategy, not fortune
  const agent = strategyFrames(8, 3, oneStop(4, "HARD"));
  const baseline = strategyFrames(8, 5, oneStop(4, "HARD"));
  expect(findDivergenceLap(agent, baseline)).toBeNull();
});

const COMPOUNDS = ["SOFT", "MEDIUM", "HARD"];

function randomStrategy(rng: () => number, laps: number): EgoStrategyFixture {
  const stopCount = Math.floor(rng() * 3);
  const stopLaps = new Set<number>();
  while (stopLaps.size < stopCount) stopLaps.add(2 + Math.floor(rng() * (laps - 1)));
  return {
    startCompound: COMPOUNDS[Math.floor(rng() * COMPOUNDS.length)],
    stops: [...stopLaps]
      .sort((a, b) => a - b)
      .map((lap) => ({ lap, compound: COMPOUNDS[Math.floor(rng() * COMPOUNDS.length)] })),
  };
}

function egoSignature(frames: ReturnType<typeof strategyFrames>, lapIndex: number): string {
  const ego = frames[lapIndex].cars[0];
  return `${ego.in_pit}|${ego.compound}|${ego.tyre_age}`;
}

test("findDivergenceLap matches a naive first-difference over random schedules", () => {
  for (let trial = 0; trial < 150; trial++) {
    const seed = 61_000 + trial;
    const rng = mulberry32(seed);
    const agentLaps = 5 + Math.floor(rng() * 20);
    const baselineLaps = 5 + Math.floor(rng() * 20);
    const agentStrategy = randomStrategy(rng, agentLaps);
    // a third of the trials share one strategy, so the null branch gets real coverage
    const baselineStrategy =
      rng() < 0.34
        ? {
            startCompound: agentStrategy.startCompound,
            stops: agentStrategy.stops.map((stop) => ({ ...stop })),
          }
        : randomStrategy(rng, baselineLaps);

    const agent = strategyFrames(agentLaps, 3, agentStrategy);
    const baseline = strategyFrames(baselineLaps, 5, baselineStrategy);

    const shared = Math.min(agentLaps, baselineLaps);
    let expected: number | null = null;
    for (let i = 0; i < shared; i++) {
      if (egoSignature(agent, i) !== egoSignature(baseline, i)) {
        expected = i + 1;
        break;
      }
    }
    expect(findDivergenceLap(agent, baseline), `seed ${seed}`).toBe(expected);
  }
});

test("deltaSeries is baseline minus agent: P5 against P3 reads +2, truncated to the shared range", () => {
  const agent = strategyFrames(4, 3, oneStop(2, "HARD"));
  const baseline = strategyFrames(6, 5, oneStop(3, "HARD"));
  const series = deltaSeries(agent, baseline);
  expect(series.map((point) => point.lap)).toEqual([1, 2, 3, 4]);
  for (const point of series) {
    expect(point.delta).toBe(2); // positive means the agent runs ahead
  }
});
