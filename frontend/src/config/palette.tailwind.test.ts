// @vitest-environment node
// the fs read needs file: module URLs, which the default jsdom environment rewrites

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { expect, test } from "vitest";

import { COMPOUND_COLOURS, PALETTE } from "./palette";

// Importing palette.ts into tailwind.config.js directly needs allowJs gymnastics
// across the Tailwind/Vite/TS boundary, so the two files hold the literals twice and
// this test is the joint. Drift here means a utility class and an inline chart hex
// stop agreeing, which is invisible until someone photographs the dashboard.
const tailwindConfig = readFileSync(
  fileURLToPath(new URL("../../tailwind.config.js", import.meta.url)),
  "utf8",
);

test("tailwind exposes every palette token under the senna namespace", () => {
  const sennaAt = tailwindConfig.indexOf("senna:");
  expect(sennaAt, "tailwind.config.js has no senna colour namespace").toBeGreaterThan(-1);
  const namespace = tailwindConfig.slice(sennaAt);

  for (const [token, hex] of Object.entries(PALETTE)) {
    expect(namespace, `senna.${token}`).toMatch(
      new RegExp(`\\b${token}\\s*:\\s*["']${hex}["']`, "i"),
    );
  }
});

test("every palette token is a six-digit hex", () => {
  for (const [token, hex] of Object.entries(PALETTE)) {
    expect(hex, token).toMatch(/^#[0-9a-f]{6}$/i);
  }
});

// The served compound strings, senna/env/scenario.py:21 by way of serve/frames.py:61.
// A misspelled key here paints a stint with `undefined` and nothing else would notice.
test("compound colours are keyed by the five served compound names", () => {
  expect(Object.keys(COMPOUND_COLOURS).sort()).toEqual([
    "HARD",
    "INTERMEDIATE",
    "MEDIUM",
    "SOFT",
    "WET",
  ]);
  for (const [compound, hex] of Object.entries(COMPOUND_COLOURS)) {
    expect(hex, compound).toMatch(/^#[0-9a-f]{6}$/i);
  }
});
