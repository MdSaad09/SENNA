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

test("the honesty footer quotes the statement verbatim with per-head fidelity and version", () => {
  render(<DecisionCardPanel card={decisionCardPitLap} />);
  const honesty = screen.getByTestId("card-honesty");
  expect(honesty).toHaveTextContent(decisionCardPitLap.honesty.statement);
  expect(honesty.textContent).toMatch(/93(\.0)?\s*%/); // pit head fidelity
  expect(honesty.textContent).toMatch(/88(\.0)?\s*%/); // mode head fidelity
  expect(honesty).toHaveTextContent("test-model");
});
