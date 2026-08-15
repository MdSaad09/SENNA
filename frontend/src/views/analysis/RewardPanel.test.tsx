import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";

import RewardPanel from "./RewardPanel";

afterEach(cleanup);

// The reward has exactly three terms (root CLAUDE.md, senna/env/race_env.py:357-363),
// and `total` is the sum the env appends — not a fourth term. The F23 reference
// screenshot decomposes reward into six invented terms, which is the defect this
// panel exists to avoid.
const SERVED_TERMS = { pace: 0.42, position: -0.13, terminal: 7.2, total: 7.49 };

function termRows(): HTMLElement[] {
  return within(screen.getByTestId("reward-terms")).getAllByRole("listitem");
}

test("the panel lists one row per served term", () => {
  render(<RewardPanel terms={SERVED_TERMS} />);
  expect(termRows().map((row) => row.getAttribute("data-term"))).toEqual([
    "pace",
    "position",
    "terminal",
  ]);
});

test("the derived total is not one of the terms", () => {
  render(<RewardPanel terms={SERVED_TERMS} />);
  expect(termRows()).toHaveLength(3);
  expect(within(screen.getByTestId("reward-terms")).queryByText(/total/i)).toBeNull();
});

test("a payload missing a term invents no label for it", () => {
  // reward_mode "terminal_only" and the v2 shaping serve different key sets; the
  // panel names what arrived and nothing else
  render(<RewardPanel terms={{ pace: 0.42, position: -0.13 }} />);
  expect(termRows().map((row) => row.getAttribute("data-term"))).toEqual(["pace", "position"]);
  expect(screen.queryByText(/terminal/i)).toBeNull();
});

test("an unexpected term is shown under its own key, not captioned or hidden", () => {
  // F08's penalty arm appends a fourth key (race_env.py:365, constraints="penalty").
  // build_env never sets that on the serving path, so this is unreachable today — but if
  // it ever arrives, printing it raw is the honest failure: inventing a caption would put
  // words in the env's mouth, and dropping it would hide a term from a decomposition
  // whose whole claim is that it shows all of them.
  render(<RewardPanel terms={{ pace: 0.4, position: -0.1, terminal: 7.2, violation_penalty: -2 }} />);
  const rows = termRows();
  expect(rows.map((row) => row.getAttribute("data-term"))).toEqual([
    "pace",
    "position",
    "terminal",
    "violation_penalty",
  ]);
  expect(rows[3]).toHaveTextContent("violation_penalty");
});
