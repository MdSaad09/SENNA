import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";

import { decisionCardPitLap, decisionCardStayOut } from "../../test/apiFixtures";
import DecisionCardPanel from "./DecisionCardPanel";

afterEach(cleanup);

test("the card shows the decision line and the plain-language sentence (A-03)", () => {
  render(<DecisionCardPanel card={decisionCardPitLap} />);
  expect(screen.getByText(decisionCardPitLap.decision)).toBeInTheDocument();
  expect(screen.getByText(decisionCardPitLap.plain_language)).toBeInTheDocument();
});

test("driver bars are exactly the served pairs, in served order", () => {
  render(<DecisionCardPanel card={decisionCardPitLap} />);
  for (const [head, served] of [
    ["pit", decisionCardPitLap.drivers.pit],
    ["mode", decisionCardPitLap.drivers.mode],
  ] as const) {
    const rows = within(screen.getByTestId(`card-drivers-${head}`)).getAllByRole("listitem");
    expect(rows).toHaveLength(served.length); // the server already trimmed to five
    served.forEach(([name], index) => expect(rows[index]).toHaveTextContent(name));
  }
});

test("flip lines render on the pit-lap card and only there", () => {
  const { unmount } = render(<DecisionCardPanel card={decisionCardPitLap} />);
  for (const line of decisionCardPitLap.flip) {
    expect(screen.getByText(line)).toBeInTheDocument();
  }
  unmount();

  // the stay-out card carries no flips (serving.yaml flip_on_pit_only) — none appear
  render(<DecisionCardPanel card={decisionCardStayOut} />);
  for (const line of decisionCardPitLap.flip) {
    expect(screen.queryByText(line)).toBeNull();
  }
});

test("the honesty footer quotes the statement verbatim with the model version", () => {
  // the fidelity figures moved to the badge (F15); the statement and version stay here
  render(<DecisionCardPanel card={decisionCardPitLap} />);
  const honesty = screen.getByTestId("card-honesty");
  expect(honesty).toHaveTextContent(decisionCardPitLap.honesty.statement);
  expect(honesty).toHaveTextContent("test-model");
});

test("the fidelity badge carries both served agreement figures (5.13)", () => {
  render(<DecisionCardPanel card={decisionCardPitLap} />);
  const badge = screen.getByTestId("fidelity-badge");
  // the served honesty.fidelity pair as percentages: pit 0.93, mode 0.88 — same
  // data as the old monospace footer line, no new numbers
  expect(badge.textContent).toMatch(/93(\.0)?\s*%/);
  expect(badge.textContent).toMatch(/88(\.0)?\s*%/);
  // the honesty statement itself stays rendered verbatim alongside the badge
  expect(screen.getByText(decisionCardPitLap.honesty.statement)).toBeInTheDocument();
});
