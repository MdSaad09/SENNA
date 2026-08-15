// The 5.13 first beat, made measurable: a cold Chrome opens the demo deep link and
// sees cars on track before the beat ends. Runs only through `make demo-check`
// against a warmed local stack (scripts/warm_demo.sh — a cold link blocks until the
// simulation completes, E-15/E-16); never vitest, never CI. Playwright's config
// supplies the baseURL.

import { expect, test } from "@playwright/test";

// sourced — spec 5.13's first beat spans 0-15 s of the demo
const DEMO_BEAT_BUDGET_MS = 15_000;

// stylised — the 5.13 storyboard's mid-race entry; the ship-time demo pick (F15 plan:
// committed ribbon, native fits, ASCII slug). Seed 55's agent stop is lap 10 — the
// latest of the auditioned bank — so the lap-8 seek lands just before the pit call.
// Keep in sync with scripts/warm_demo.sh, docs/demo/script.md and the README.
const DEMO_URL = "/strategy/live?circuit=bahrain_grand_prix&seed=55&lap=8&speed=30";

test("the demo deep link puts cars on track inside the 15-second first beat (5.13)", async ({
  page,
}) => {
  // the whole beat — navigation included — must land inside the budget
  test.setTimeout(DEMO_BEAT_BUDGET_MS);
  await page.goto(DEMO_URL);

  // the one canvas the live view owns (F-28)
  await expect(page.locator("canvas")).toBeVisible({ timeout: DEMO_BEAT_BUDGET_MS });

  // the transport mounts only once the first frame of cars is buffered — the
  // DOM-visible proof the scene container is populated (the cars themselves render
  // inside WebGL, invisible to selectors); this doubles as the harness for the
  // INDEX open item on the near-empty Chrome canvas
  await expect(page.getByRole("slider", { name: /scrub/i })).toBeVisible({
    timeout: DEMO_BEAT_BUDGET_MS,
  });
});
