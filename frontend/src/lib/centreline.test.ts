import { expect, test } from "vitest";

import {
  squareCentres,
  squareCumS,
  squareRibbonPositions,
  squareTotal,
} from "../test/ribbonFixture";
import { buildCentreline } from "./centreline";

const centreline = buildCentreline(squareRibbonPositions);

function expectPoint(actual: [number, number, number], expected: [number, number, number]) {
  for (let axis = 0; axis < 3; axis++) {
    expect(actual[axis]).toBeCloseTo(expected[axis], 5);
  }
}

test("recovers each station as the midpoint of its interleaved edge pair", () => {
  expect(centreline.stations).toBe(4);
  squareCumS.forEach((s_m, station) => {
    expectPoint(centreline.sampleAt(s_m), squareCentres[station]);
  });
});

test("accumulates arc length around the closed square", () => {
  const cumS = Array.from(centreline.cumS);
  expect(cumS).toHaveLength(4);
  squareCumS.forEach((s_m, station) => {
    expect(cumS[station]).toBeCloseTo(s_m, 5);
  });
  expect(centreline.total).toBeCloseTo(squareTotal, 5);
});

test("sampleAt interpolates linearly between stations", () => {
  expectPoint(centreline.sampleAt(5), [5, 0, 0]);
  expectPoint(centreline.sampleAt(15), [10, 5, 0]);
  expectPoint(centreline.sampleAt(35), [0, 5, 0]); // the closing segment back to the start
});

test("sampleAt wraps the closed ring for s beyond the lap and for negative s", () => {
  expectPoint(centreline.sampleAt(squareTotal), centreline.sampleAt(0));
  expectPoint(centreline.sampleAt(squareTotal + 5), centreline.sampleAt(5));
  expectPoint(centreline.sampleAt(-5), centreline.sampleAt(35));
});

test("tangentAt points along travel with unit length", () => {
  expectPoint(centreline.tangentAt(5), [1, 0, 0]);
  expectPoint(centreline.tangentAt(15), [0, 1, 0]);
  expectPoint(centreline.tangentAt(25), [-1, 0, 0]);
  expectPoint(centreline.tangentAt(35), [0, -1, 0]);

  const wrapped = centreline.tangentAt(-3);
  const norm = Math.hypot(wrapped[0], wrapped[1], wrapped[2]);
  expect(norm).toBeCloseTo(1, 5);
});

test("edge samples straddle the centre: left and right average to the centreline", () => {
  for (const s_m of [0, 7, 13, 26, 38]) {
    const left = centreline.leftAt(s_m);
    const right = centreline.rightAt(s_m);
    const centre = centreline.sampleAt(s_m);
    for (let axis = 0; axis < 3; axis++) {
      expect((left[axis] + right[axis]) / 2, `s=${s_m} axis ${axis}`).toBeCloseTo(
        centre[axis],
        5,
      );
    }
  }
  // fixture layout: at the origin corner the left edge sits 1 m outward on the diagonal
  expectPoint(centreline.leftAt(0), [-Math.SQRT1_2, -Math.SQRT1_2, 0]);
});
