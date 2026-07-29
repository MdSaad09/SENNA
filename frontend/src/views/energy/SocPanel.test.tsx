import { expect, test } from "vitest";

import { energyProfile } from "../../test/apiFixtures";
import { socTooltip } from "./SocPanel";

// The 5.13 energy beat hovers a lap and reads "banked energy before an attack" — so
// the tooltip must name the mode, not just the SOC number. recharts renders nothing
// measurable under jsdom, so the exported formatter is the seam under test; the
// panel's <Tooltip> delegates to it.

test("the SOC tooltip names the served energy mode next to the value", () => {
  // fixture lap 2: soc 0.5 MJ after a heavy deploy, mode 2 — the attack lap
  const attackLap = energyProfile.laps[1];
  expect(socTooltip(attackLap)).toContain("0.50 MJ");
  expect(socTooltip(attackLap)).toContain("attack");
});

test("the mode name follows the served numeric mode, lap by lap", () => {
  const fullLap = energyProfile.laps[0]; // mode 1
  const defendLap = energyProfile.laps[5]; // mode 3
  expect(socTooltip(fullLap)).toContain("run balanced");
  expect(socTooltip(defendLap)).toContain("defend");
  expect(socTooltip({ ...fullLap, mode: 0 })).toContain("conserve");
});
