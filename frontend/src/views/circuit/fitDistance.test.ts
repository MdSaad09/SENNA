import { expect, test } from "vitest";

import { CAMERA, RIBBON_VIEWPORT_FILL } from "../../config/constants";
import { fitDistance } from "./fitDistance";

// Radii of the two circuits that bracket the library: Monaco is the tightest ribbon and
// Spa the longest, and the fixed pre-F23 camera at [0, 900, 900] (distance ~1273) was
// chosen for neither.
const MONACO_R = 500;
const SPA_R = 1500;

test("a bigger circuit is framed from further back, in proportion", () => {
  const near = fitDistance(MONACO_R, CAMERA.fov, 16 / 9, RIBBON_VIEWPORT_FILL);
  const far = fitDistance(SPA_R, CAMERA.fov, 16 / 9, RIBBON_VIEWPORT_FILL);
  expect(far / near).toBeCloseTo(SPA_R / MONACO_R, 10);
});

test("the fill is a fraction of the frustum's tangency, which is what the fit solves", () => {
  const distance = fitDistance(MONACO_R, CAMERA.fov, 16 / 9, RIBBON_VIEWPORT_FILL);
  const half = (CAMERA.fov * Math.PI) / 360;
  // the tangency relation the function inverts: sin(angular radius) = fill * sin(half)
  expect(MONACO_R / distance).toBeCloseTo(RIBBON_VIEWPORT_FILL * Math.sin(half), 10);
});

test("the sphere's projected radius lands where the constant's comment claims", () => {
  // A sphere's tangency distance is not a linear fraction of the frustum, so a fill of
  // 0.82 does not put 82% of the panel height under the circuit. Measured here so the
  // number the view prints is the one that ships, not the one that sounds tidy.
  const half = (CAMERA.fov * Math.PI) / 360;
  const distance = fitDistance(MONACO_R, CAMERA.fov, 16 / 9, RIBBON_VIEWPORT_FILL);
  const projected = Math.tan(Math.asin(MONACO_R / distance)) / Math.tan(half);
  expect(projected).toBeCloseTo(0.79, 2);
});

test("a portrait panel is bound by its width, so it pulls back further", () => {
  const landscape = fitDistance(MONACO_R, CAMERA.fov, 16 / 9, RIBBON_VIEWPORT_FILL);
  const portrait = fitDistance(MONACO_R, CAMERA.fov, 9 / 16, RIBBON_VIEWPORT_FILL);
  expect(portrait).toBeGreaterThan(landscape);
});

test("a square panel makes the two constraints agree", () => {
  const square = fitDistance(MONACO_R, CAMERA.fov, 1, RIBBON_VIEWPORT_FILL);
  const halfAngle = (CAMERA.fov * Math.PI) / 360;
  expect(square).toBeCloseTo(MONACO_R / (RIBBON_VIEWPORT_FILL * Math.sin(halfAngle)), 10);
});

test("a degenerate ribbon does not divide by zero", () => {
  // a GLB that failed to load leaves radius 0; the camera should stay where it is
  expect(fitDistance(0, CAMERA.fov, 16 / 9, RIBBON_VIEWPORT_FILL)).toBe(0);
  expect(fitDistance(MONACO_R, CAMERA.fov, 16 / 9, 0)).toBe(0);
});

test("the fit clears the near and far planes for the whole library", () => {
  for (const radius of [MONACO_R, SPA_R]) {
    const distance = fitDistance(radius, CAMERA.fov, 16 / 9, RIBBON_VIEWPORT_FILL);
    expect(distance).toBeGreaterThan(CAMERA.near);
    expect(distance + radius).toBeLessThan(CAMERA.far);
  }
});
