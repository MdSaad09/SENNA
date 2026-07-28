import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, test } from "vitest";

import App from "./App";

afterEach(cleanup);

const VIEW_LABELS = ["circuit", "replay", "energy", "tyres", "live", "counterfactual"];

// the shell needs a router for its NavLinks; MemoryRouter is the lightest one
function renderShell(at = "/") {
  render(
    <MemoryRouter initialEntries={[at]}>
      <App />
    </MemoryRouter>,
  );
}

test("shows the SENNA title", () => {
  renderShell();
  expect(screen.getByText("SENNA")).toBeInTheDocument();
});

test("keeps the disclaimer footer and offers all six views", () => {
  renderShell();
  // the canonical R-07/F-29 wording (F15 decision 2), verbatim — it also fronts the
  // README and the video end card, so the three may never drift apart
  expect(
    screen.getByText(
      "SENNA is an unofficial project and is not associated in any way with the Formula 1 companies, the FIA or any team",
    ),
  ).toBeInTheDocument();
  for (const label of VIEW_LABELS) {
    expect(screen.getByRole("link", { name: label })).toBeInTheDocument();
  }
});

test("nav links carry the current query so one click keeps the run (5.13)", () => {
  // the storyboard's "one click to the counterfactual view" only works if ?run=
  // survives the switch; every view reads what it needs and ignores the rest
  renderShell("/live?run=7");
  for (const label of VIEW_LABELS) {
    expect(screen.getByRole("link", { name: label })).toHaveAttribute("href", `/${label}?run=7`);
  }
});
