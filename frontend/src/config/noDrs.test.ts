// @vitest-environment node
// the fs walk needs file: module URLs, which the default jsdom environment rewrites

import { readFileSync, readdirSync } from "node:fs";
import { basename, extname, join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test } from "vitest";

const frontendRoot = fileURLToPath(new URL("../..", import.meta.url));
const srcRoot = join(frontendRoot, "src");

function walk(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = join(dir, entry.name);
    return entry.isDirectory() ? walk(full) : [full];
  });
}

const SHIPPED_EXTENSIONS = [".ts", ".tsx", ".css"];

function shipsToTheBrowser(file: string): boolean {
  if (!SHIPPED_EXTENSIONS.includes(extname(file))) return false;
  if (relative(srcRoot, file).split(sep)[0] === "test") return false; // fixtures never ship
  return !basename(file).includes(".test.");
}

// This passes on day one. It exists because the F23 reference screenshots carry two
// DRS mentions — a parameter card reading "DRS 1 zones" and a legend line — and
// copying either would put a feature that does not exist in 2026 on screen. The 2026
// overtaking aid is Manual Override and the circuit annotation is X-mode sections.
test("no shipped frontend file mentions DRS (F23: there is no DRS in 2026)", () => {
  // a word boundary, not a lowercase substring: "drs" sits inside ordinary
  // identifiers and the substring compare the F-29 walk uses would false-positive
  const drs = /\bDRS\b/;
  const shipped = [...walk(srcRoot).filter(shipsToTheBrowser), join(frontendRoot, "index.html")];
  expect(shipped.length).toBeGreaterThan(0);

  for (const file of shipped) {
    const text = readFileSync(file, "utf8");
    expect(drs.test(text), `${relative(frontendRoot, file)} mentions DRS`).toBe(false);
  }
});
