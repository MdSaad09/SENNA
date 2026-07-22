import { expect, test } from "vitest";

import { mulberry32 } from "../test/prng";
import { monotoneCubic, unwrapProgress } from "./progress";

const frac = (value: number) => value - Math.floor(value);

// Seeded property loops instead of a fast-check dependency (plan, test 4): every
// failure message carries the seed, so a red run replays exactly.
const UNWRAP_CASES = 500;
const UNWRAP_BASE_SEED = 271_000;

test("unwrapped progress climbs monotonically and round-trips its fractions", () => {
  for (let i = 0; i < UNWRAP_CASES; i++) {
    const seed = UNWRAP_BASE_SEED + i;
    const rng = mulberry32(seed);
    const label = `seed ${seed}`;

    // true per-lap advance is 1 + U(-0.3, 0.3): lapped and lapping cars included
    const laps = 5 + Math.floor(rng() * 60);
    const truth: number[] = [rng()];
    for (let lap = 1; lap < laps; lap++) {
      truth.push(truth[lap - 1] + 1 + (rng() - 0.5) * 0.6);
    }
    const fractions = truth.map(frac);

    const unwrapped = unwrapProgress(fractions);
    expect(unwrapped, label).toHaveLength(laps);
    expect(unwrapped[0], label).toBe(fractions[0]);

    for (let lap = 1; lap < laps; lap++) {
      const advance = unwrapped[lap] - unwrapped[lap - 1];
      expect(advance, label).toBeGreaterThan(0.5);
      expect(advance, label).toBeLessThan(1.5);
      // the mod-1 wrap loses nothing: fractions survive, advances are recovered
      expect(Math.abs(frac(unwrapped[lap]) - fractions[lap]), label).toBeLessThan(1e-9);
      expect(Math.abs(advance - (truth[lap] - truth[lap - 1])), label).toBeLessThan(1e-9);
    }
  }
});

test("the interpolant is exact at its knots, flats included", () => {
  const xs = [0, 1, 2, 4];
  const ys = [0, 1, 1, 5];
  const interpolate = monotoneCubic(xs, ys);
  xs.forEach((x, knot) => {
    expect(interpolate(x)).toBeCloseTo(ys[knot], 9);
  });
});

test("a step profile never overshoots — the reason Catmull-Rom was rejected", () => {
  const interpolate = monotoneCubic([0, 1, 2, 3], [0, 0, 1, 1]);
  let previous = interpolate(0);
  for (let step = 1; step <= 400; step++) {
    const value = interpolate((step / 400) * 3);
    expect(value).toBeGreaterThanOrEqual(-1e-9);
    expect(value).toBeLessThanOrEqual(1 + 1e-9);
    expect(value).toBeGreaterThanOrEqual(previous - 1e-12); // a car never reverses
    previous = value;
  }
});

test("evaluation clamps outside the knot range", () => {
  const interpolate = monotoneCubic([2, 3, 5], [10, 11, 14]);
  expect(interpolate(-100)).toBeCloseTo(10, 9);
  expect(interpolate(1.999)).toBeCloseTo(10, 9);
  expect(interpolate(5.001)).toBeCloseTo(14, 9);
  expect(interpolate(100)).toBeCloseTo(14, 9);
});

const CUBIC_CASES = 100;
const CUBIC_BASE_SEED = 846_000;

test("random non-decreasing knots stay non-decreasing under dense evaluation", () => {
  for (let i = 0; i < CUBIC_CASES; i++) {
    const seed = CUBIC_BASE_SEED + i;
    const rng = mulberry32(seed);
    const label = `seed ${seed}`;

    const knots = 2 + Math.floor(rng() * 9);
    const xs: number[] = [rng()];
    const ys: number[] = [rng()];
    for (let knot = 1; knot < knots; knot++) {
      xs.push(xs[knot - 1] + 0.1 + rng());
      ys.push(ys[knot - 1] + (rng() < 0.3 ? 0 : rng())); // occasional flat spans
    }

    const interpolate = monotoneCubic(xs, ys);
    const from = xs[0] - 1;
    const span = xs[knots - 1] + 1 - from;
    let previous = interpolate(from);
    for (let step = 1; step <= 200; step++) {
      const value = interpolate(from + (step / 200) * span);
      expect(value, label).toBeGreaterThanOrEqual(previous - 1e-12);
      expect(value, label).toBeGreaterThanOrEqual(ys[0] - 1e-9);
      expect(value, label).toBeLessThanOrEqual(ys[knots - 1] + 1e-9);
      previous = value;
    }
  }
});
