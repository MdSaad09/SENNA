// @vitest-environment node
// the fs walk needs file: module URLs, which the default jsdom environment rewrites

import { readFileSync, readdirSync } from "node:fs";
import { basename, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test } from "vitest";

const frontendRoot = fileURLToPath(new URL("../..", import.meta.url));
const configRoot = fileURLToPath(new URL(".", import.meta.url));

// The root CLAUDE.md rule: an inline constant is a defect, every number names its
// origin. configs/*.yaml carries the tag for the backend; the browser cannot read
// yaml, so config/*.ts is where the frontend's numbers live (F11 divergence 6). The
// convention has been hand-followed since F11 — this walk is what enforces it.
const PROVENANCE_TAG = /\/\/.*\b(sourced|fitted|stylised|operational)\b/;
// `export const A = 1, B = 2` declares two; indented exports and re-exports also
// escaped the anchored form this started with
const EXPORTED_CONST = /^\s*export const (\w+)/;

function configModules(): string[] {
  return readdirSync(configRoot)
    .filter((name) => name.endsWith(".ts") && !name.includes(".test."))
    .map((name) => join(configRoot, name));
}

/** The comment block introducing the constant at `index`, plus its own line. Grouped
 * constants share one block, which is how constants.ts already reads, so the tag may sit
 * anywhere in the run of comment lines directly above rather than on one exact line.
 *
 * Deliberately upward-only. The first cut of this walk scanned downward as well, so a
 * tag written *below* an export satisfied it — the constant could be introduced by
 * nothing at all. Grouping is still allowed, because constants.ts uses it on purpose
 * (the three WS backoff values share one rationale, and splitting it three ways would
 * say less), so the honest limit is this: a blank line ends the block, and an export
 * cannot inherit a tag it is separated from. */
function introducing(lines: string[], index: number): string[] {
  const block = [lines[index]];
  for (let above = index - 1; above >= 0 && lines[above].trim() !== ""; above--) {
    block.push(lines[above]);
  }
  return block;
}

test("every exported frontend constant names its provenance", () => {
  const modules = configModules();
  expect(modules.length).toBeGreaterThan(1); // constants.ts and liveries.ts at least

  for (const file of modules) {
    const lines = readFileSync(file, "utf8").split("\n");
    const where = relative(frontendRoot, file);
    const exported: string[] = [];

    lines.forEach((line, index) => {
      const match = EXPORTED_CONST.exec(line);
      if (match === null) return;
      exported.push(match[1]);
      const tagged = introducing(lines, index).some((near) => PROVENANCE_TAG.test(near));
      expect(
        tagged,
        `${where}: ${match[1]} has no sourced/fitted/stylised/operational comment`,
      ).toBe(true);
    });

    expect(exported.length, `${where} exports no constants`).toBeGreaterThan(0);
  }
});

test("the walk covers the palette as well as the older config modules", () => {
  // named explicitly so deleting palette.ts cannot quietly shrink the walk to nothing
  const covered = configModules().map((file) => basename(file));
  expect(covered).toContain("constants.ts");
  expect(covered).toContain("liveries.ts");
  expect(covered).toContain("palette.ts");
});
