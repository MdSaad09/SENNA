// The maths behind View 4, kept in plain TS so it is testable and so the vertex shader
// in GripSurface.tsx has a twin to check against. grip(age) = 1 - a*age^b is the served
// fit (T5); the temperature axis is a stylised illustration (decision 1) that must not
// touch any readout — hence tempGripFactor is exactly 1 at the reference slice.

import {
  GRIP_AGE_SAMPLES,
  GRIP_TEMP_SAMPLES,
  TYRE_TEMP_AXIS_MAX_C,
  TYRE_TEMP_AXIS_MIN_C,
  TYRE_TEMP_GRIP_PENALTY,
  TYRE_TEMP_REF_C,
} from "../config/constants";

function clamp01(value: number): number {
  return value < 0 ? 0 : value > 1 ? 1 : value;
}

/** The served power law grip(age) = 1 - a*age^b, clipped to [0, 1] exactly as the sim's
 * grip_est (senna/env/dynamics.py). This is the fitted 30 C slice — every hover and
 * readout number in the view reads off it, never off the stylised temperature axis. */
export function fittedGrip(a: number, b: number, age: number): number {
  return clamp01(1 - a * age ** b);
}

/** The stylised temperature response: exactly 1 at the reference so the surface equals
 * the fitted curve there, dipping at most TYRE_TEMP_GRIP_PENALTY toward the axis
 * extremes. The fit has no temperature term — this is illustration, labelled as such
 * on the view. The GLSL in GripSurface.tsx mirrors this function. */
export function tempGripFactor(tempC: number): number {
  const span = Math.max(
    TYRE_TEMP_REF_C - TYRE_TEMP_AXIS_MIN_C,
    TYRE_TEMP_AXIS_MAX_C - TYRE_TEMP_REF_C,
  );
  const distance = Math.abs(tempC - TYRE_TEMP_REF_C) / span;
  return 1 - TYRE_TEMP_GRIP_PENALTY * distance * distance;
}

export function surfaceGrip(a: number, b: number, age: number, tempC: number): number {
  return clamp01(fittedGrip(a, b, age) * tempGripFactor(tempC));
}

export interface GripSurface {
  positions: Float32Array; // a flat unit grid (x, y in [0, 1], z 0); the shader lifts z
  indices: Uint32Array;
  ageSamples: number;
  tempSamples: number;
  ageMax: number;
  cliffAge: number;
}

/** The flat unit grid the vertex shader lifts into the grip surface. ageMax is the
 * served cliff, so the age axis runs exactly to where the sim fails the tyre; the
 * shader reads a vertex's (x, y) as (age fraction, temperature fraction). */
export function buildGripSurface(curve: { a: number; b: number; cliff_age: number }): GripSurface {
  const ageSamples = GRIP_AGE_SAMPLES;
  const tempSamples = GRIP_TEMP_SAMPLES;

  const positions = new Float32Array(ageSamples * tempSamples * 3);
  for (let i = 0; i < ageSamples; i++) {
    const u = i / (ageSamples - 1);
    for (let j = 0; j < tempSamples; j++) {
      const base = (i * tempSamples + j) * 3;
      positions[base] = u;
      positions[base + 1] = j / (tempSamples - 1);
      positions[base + 2] = 0;
    }
  }

  const indices = new Uint32Array((ageSamples - 1) * (tempSamples - 1) * 6);
  let cursor = 0;
  for (let i = 0; i < ageSamples - 1; i++) {
    for (let j = 0; j < tempSamples - 1; j++) {
      const nearLeft = i * tempSamples + j;
      const nearRight = nearLeft + 1;
      const farLeft = nearLeft + tempSamples;
      const farRight = farLeft + 1;
      indices[cursor++] = nearLeft;
      indices[cursor++] = farLeft;
      indices[cursor++] = nearRight;
      indices[cursor++] = nearRight;
      indices[cursor++] = farLeft;
      indices[cursor++] = farRight;
    }
  }

  return {
    positions,
    indices,
    ageSamples,
    tempSamples,
    ageMax: curve.cliff_age,
    cliffAge: curve.cliff_age,
  };
}
