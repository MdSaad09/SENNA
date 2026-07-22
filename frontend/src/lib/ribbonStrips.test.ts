import { expect, test } from "vitest";

import { squareRibbonPositions } from "../test/ribbonFixture";
import { buildCentreline } from "./centreline";
import { buildStrip } from "./ribbonStrips";

const centreline = buildCentreline(squareRibbonPositions);
const LIFT_M = 0.2;
const WIDTH_FRACTION = 0.5;

function strip(zones: { start_m: number; end_m: number }[]) {
  return buildStrip(centreline, zones, { lift_m: LIFT_M, width_fraction: WIDTH_FRACTION });
}

// both vertices of a sample sit symmetrically about the centreline, so their
// midpoint recovers the centre point the sample was taken at
function pairMidpointXY(positions: Float32Array, pair: number): [number, number] {
  const at = pair * 6;
  return [
    (positions[at] + positions[at + 3]) / 2,
    (positions[at + 1] + positions[at + 4]) / 2,
  ];
}

function expectXY(actual: [number, number], expected: [number, number], label: string) {
  expect(actual[0], label).toBeCloseTo(expected[0], 5);
  expect(actual[1], label).toBeCloseTo(expected[1], 5);
}

test("a zone samples its ends plus every station strictly inside", () => {
  const built = strip([{ start_m: 8, end_m: 12 }]);
  expect(built.positions).toBeInstanceOf(Float32Array);
  expect(built.indices).toBeInstanceOf(Uint32Array);

  // samples at s = 8, the station at s = 10, and s = 12 -> 6 vertices
  expect(built.positions).toHaveLength(18);
  expectXY(pairMidpointXY(built.positions, 0), [8, 0], "s=8");
  expectXY(pairMidpointXY(built.positions, 1), [10, 0], "s=10");
  expectXY(pairMidpointXY(built.positions, 2), [10, 2], "s=12");

  // 3 samples -> 2 quads -> 4 triangles, all indices inside the vertex range
  expect(built.indices).toHaveLength(12);
  for (const vertex of built.indices) {
    expect(vertex).toBeLessThan(built.positions.length / 3);
  }
});

test("vertices lerp from the centre toward each edge by width_fraction", () => {
  const built = strip([{ start_m: 8, end_m: 12 }]);
  const centre = centreline.sampleAt(8);
  const left = centreline.leftAt(8);
  const right = centreline.rightAt(8);

  for (let axis = 0; axis < 2; axis++) {
    const towardLeft = centre[axis] + WIDTH_FRACTION * (left[axis] - centre[axis]);
    const towardRight = centre[axis] + WIDTH_FRACTION * (right[axis] - centre[axis]);
    expect(built.positions[axis], `left axis ${axis}`).toBeCloseTo(towardLeft, 5);
    expect(built.positions[3 + axis], `right axis ${axis}`).toBeCloseTo(towardRight, 5);
  }
});

test("every vertex floats exactly lift_m above the ribbon", () => {
  const built = strip([{ start_m: 8, end_m: 12 }]);
  for (let component = 2; component < built.positions.length; component += 3) {
    // the fixture centreline lies at z = 0, so z is the lift itself
    expect(built.positions[component]).toBeCloseTo(LIFT_M, 6);
  }
});

test("a zone crossing s = 0 splits into two runs inside one geometry", () => {
  const built = strip([{ start_m: 38, end_m: 2 }]);

  // run one covers [38, 40], run two covers [0, 2]; no station falls strictly
  // inside either, so 4 samples -> 8 vertices
  expect(built.positions).toHaveLength(24);
  expectXY(pairMidpointXY(built.positions, 0), [0, 2], "s=38");
  expectXY(pairMidpointXY(built.positions, 1), [0, 0], "s=40");
  expectXY(pairMidpointXY(built.positions, 2), [0, 0], "s=0");
  expectXY(pairMidpointXY(built.positions, 3), [2, 0], "s=2");

  // one quad per run; no triangle may bridge the seam at s = 0
  expect(built.indices).toHaveLength(12);
  for (let tri = 0; tri < built.indices.length; tri += 3) {
    const inFirstRun = [
      built.indices[tri] < 4,
      built.indices[tri + 1] < 4,
      built.indices[tri + 2] < 4,
    ];
    expect(new Set(inFirstRun).size, `triangle at index ${tri} bridges the wrap`).toBe(1);
  }
});

test("several zones merge into one buffer without bridging triangles", () => {
  const built = strip([
    { start_m: 8, end_m: 12 },
    { start_m: 28, end_m: 32 },
  ]);

  // each zone contributes 3 samples (start, one interior station, end)
  expect(built.positions).toHaveLength(36);
  expectXY(pairMidpointXY(built.positions, 3), [2, 10], "s=28");
  expectXY(pairMidpointXY(built.positions, 4), [0, 10], "s=30");
  expectXY(pairMidpointXY(built.positions, 5), [0, 8], "s=32");

  expect(built.indices).toHaveLength(24);
  for (let tri = 0; tri < built.indices.length; tri += 3) {
    const inFirstZone = [
      built.indices[tri] < 6,
      built.indices[tri + 1] < 6,
      built.indices[tri + 2] < 6,
    ];
    expect(new Set(inFirstZone).size, `triangle at index ${tri} spans two zones`).toBe(1);
  }
});
