import { readFileSync, readdirSync } from "node:fs";
import { basename, extname, join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test } from "vitest";

import { TEAM_COLOURS, carLivery } from "./liveries";

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

// The F-29 deny list. This test is the one place in frontend/ these names may be
// spelled out; the walk above excludes test files, so the list cannot flag itself.
const FULL_MARKS = [
  "ferrari", "mercedes", "mclaren", "red bull", "redbull", "aston martin",
  "alpine", "williams", "haas", "sauber", "audi", "cadillac",
  "petronas", "pirelli", "rolex",
  "verstappen", "hamilton", "leclerc", "norris", "russell", "alonso",
  "piastri", "sainz",
];
// short marks need word boundaries and case: "rb" sits inside ordinary words
const SHORT_MARKS = [/\bRB\b/, /\bAMG\b/];

test("no team, sponsor or driver marks ship in the frontend (F-29)", () => {
  const shipped = [...walk(srcRoot).filter(shipsToTheBrowser), join(frontendRoot, "index.html")];
  expect(shipped.length).toBeGreaterThan(0);

  for (const file of shipped) {
    const text = readFileSync(file, "utf8");
    const lower = text.toLowerCase();
    const where = relative(frontendRoot, file);
    for (const mark of FULL_MARKS) {
      expect(lower.includes(mark), `${where} contains "${mark}"`).toBe(false);
    }
    for (const mark of SHORT_MARKS) {
      expect(mark.test(text), `${where} matches ${mark}`).toBe(false);
    }
  }
});

test("eleven team colours, each a unique hex value", () => {
  expect(TEAM_COLOURS).toHaveLength(11);
  for (const colour of TEAM_COLOURS) {
    expect(colour).toMatch(/^#[0-9a-f]{6}$/i);
  }
  expect(new Set(TEAM_COLOURS.map((colour) => colour.toLowerCase())).size).toBe(11);
});

test("car codes run C01 to C22, two cars per team, in the team's colour", () => {
  for (let id = 0; id < 22; id++) {
    const livery = carLivery(id);
    expect(livery.code).toBe(`C${String(id + 1).padStart(2, "0")}`);
    expect(livery.code).toMatch(/^C(0[1-9]|1\d|2[0-2])$/);
    expect(livery.team).toBe(Math.floor(id / 2));
    expect(livery.colour).toBe(TEAM_COLOURS[livery.team]);
  }
});
