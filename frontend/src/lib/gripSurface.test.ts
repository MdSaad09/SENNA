import { expect, test } from "vitest";

import {
  GRIP_AGE_SAMPLES,
  GRIP_TEMP_SAMPLES,
  TYRE_TEMP_AXIS_MAX_C,
  TYRE_TEMP_AXIS_MIN_C,
  TYRE_TEMP_REF_C,
} from "../config/constants";
import { mulberry32 } from "../test/prng";
import { buildGripSurface, fittedGrip, surfaceGrip, tempGripFactor } from "./gripSurface";

// The surface renders the served power-law grip(age) = 1 - a*age^b (T5), never raw
// laps (E-09). These tests pin the maths the vertex shader mirrors: the age slice is
// the fitted model exactly, the temperature axis only bends it, and the cliff sits
// where the sim's failure margin puts it.

test("fitted grip starts at 1 on a fresh tyre and only falls with age", () => {
  for (const [a, b] of [
    [0.000878, 1.0671],
    [0.0025, 2.4],
    [0.0, 0.3], // a degenerate transfer: no wear, grip pinned at 1
  ]) {
    expect(fittedGrip(a, b, 0)).toBe(1);
    expect(fittedGrip(a, b, 10)).toBeLessThanOrEqual(fittedGrip(a, b, 5));
  }
});

test("at the reference temperature the surface equals the fitted curve exactly", () => {
  // decision 1: every hover/readout number comes off the 30 C slice, so the stylised
  // temperature factor must be exactly 1 there — no drift into the served numbers
  expect(tempGripFactor(TYRE_TEMP_REF_C)).toBe(1);
  for (const age of [0, 3, 8, 15, 27, 40]) {
    expect(surfaceGrip(0.000754, 1.1307, age, TYRE_TEMP_REF_C)).toBe(
      fittedGrip(0.000754, 1.1307, age),
    );
  }
});

test("the stylised temperature factor stays a gentle dip, never below 1 minus the penalty", () => {
  for (const temp of [TYRE_TEMP_AXIS_MIN_C, 22, TYRE_TEMP_REF_C, 45, TYRE_TEMP_AXIS_MAX_C]) {
    const factor = tempGripFactor(temp);
    expect(factor).toBeLessThanOrEqual(1);
    expect(factor).toBeGreaterThanOrEqual(0.9); // penalty is 0.08, so the floor is 0.92
  }
});

test("grip is bounded in [0, 1] and non-increasing in age across the fitted bounds", () => {
  const seed = 0x5e0a12; // printed so a failure replays exactly
  const rng = mulberry32(seed);
  for (let trial = 0; trial < 400; trial++) {
    const a = rng() * 5; // configs/fits.yaml curve_bounds a in [0, 5]
    const b = 0.3 + rng() * 2.7; // b in [0.3, 3]
    const temp = TYRE_TEMP_AXIS_MIN_C + rng() * (TYRE_TEMP_AXIS_MAX_C - TYRE_TEMP_AXIS_MIN_C);
    let previous = Infinity;
    for (let age = 0; age <= 45; age++) {
      const grip = fittedGrip(a, b, age);
      expect(grip, `seed ${seed} a=${a} b=${b} age=${age}`).toBeGreaterThanOrEqual(0);
      expect(grip).toBeLessThanOrEqual(1);
      expect(grip).toBeLessThanOrEqual(previous + 1e-9);
      previous = grip;
      const shaded = surfaceGrip(a, b, age, temp);
      expect(shaded).toBeGreaterThanOrEqual(0);
      expect(shaded).toBeLessThanOrEqual(1);
    }
  }
});

test("the built surface is one tessellated grid running out to the served cliff", () => {
  const surface = buildGripSurface({ a: 0.000878, b: 1.0671, cliff_age: 33 });
  expect(surface.cliffAge).toBe(33);
  expect(surface.ageMax).toBe(33);
  expect(surface.ageSamples).toBe(GRIP_AGE_SAMPLES);
  expect(surface.tempSamples).toBe(GRIP_TEMP_SAMPLES);
  expect(surface.positions.length).toBe(GRIP_AGE_SAMPLES * GRIP_TEMP_SAMPLES * 3);
  expect(surface.indices.length).toBeGreaterThan(0);
});
