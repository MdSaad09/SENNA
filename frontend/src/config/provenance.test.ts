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
const EXPORTED_CONST = /^export const (\w+)/;

function configModules(): string[] {
  return readdirSync(configRoot)
    .filter((name) => name.endsWith(".ts") && !name.includes(".test."))
    .map((name) => join(configRoot, name));
}

/** The run of non-blank lines around `index` — a constant and the comment block that
 * introduces it. Grouped constants share one block, which is how constants.ts already
 * reads, so the tag may sit anywhere in the run rather than on one exact line. */
function paragraphAround(lines: string[], index: number): string[] {
  let start = index;
  while (start > 0 && lines[start - 1].trim() !== "") start--;
  let end = index;
  while (end < lines.length - 1 && lines[end + 1].trim() !== "") end++;
  return lines.slice(start, end + 1);
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
      const tagged = paragraphAround(lines, index).some((near) => PROVENANCE_TAG.test(near));
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
