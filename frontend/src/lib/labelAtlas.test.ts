import { expect, test } from "vitest";

import { atlasLayout } from "./labelAtlas";

// the full 2026 grid of generic codes; drawing the atlas needs a real 2D context,
// so jsdom pins the layout math only (plan, test 12)
const codes = Array.from({ length: 22 }, (_, id) => `C${String(id + 1).padStart(2, "0")}`);

test("the grid is big enough for every code", () => {
  const layout = atlasLayout(codes);
  expect(Number.isInteger(layout.cols)).toBe(true);
  expect(Number.isInteger(layout.rows)).toBe(true);
  expect(layout.cols).toBeGreaterThan(0);
  expect(layout.rows).toBeGreaterThan(0);
  expect(layout.cols * layout.rows).toBeGreaterThanOrEqual(codes.length);
});

test("cell sizes are sane texture fractions", () => {
  const layout = atlasLayout(codes);
  expect(layout.cellU).toBeGreaterThan(0);
  expect(layout.cellU).toBeLessThanOrEqual(1);
  expect(layout.cellV).toBeGreaterThan(0);
  expect(layout.cellV).toBeLessThanOrEqual(1);
});

test("every code gets a distinct cell that fits inside the texture", () => {
  const layout = atlasLayout(codes);
  const seen = new Set<string>();
  codes.forEach((code, index) => {
    const [u, v] = layout.uvOffset(index);
    expect(u, code).toBeGreaterThanOrEqual(0);
    expect(u, code).toBeLessThan(1);
    expect(v, code).toBeGreaterThanOrEqual(0);
    expect(v, code).toBeLessThan(1);
    expect(u + layout.cellU, code).toBeLessThanOrEqual(1 + 1e-9);
    expect(v + layout.cellV, code).toBeLessThanOrEqual(1 + 1e-9);
    seen.add(`${u},${v}`);
  });
  expect(seen.size).toBe(codes.length);
});
