import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, test } from "vitest";

import App from "./App";

afterEach(cleanup);

// F23 folds the six flat views into three tabs; the sections live on a sub-rail, so
// only these three names appear in the top nav
const TAB_LABELS = ["strategy", "circuit", "analysis"];

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

test("keeps the disclaimer footer", () => {
  renderShell();
  // the canonical R-07/F-29 wording (F15 decision 2), verbatim — it also fronts the
  // README and the video end card, so the three may never drift apart
  expect(
    screen.getByText(
      "SENNA is an unofficial project and is not associated in any way with the Formula 1 companies, the FIA or any team",
    ),
  ).toBeInTheDocument();
});

test("offers the three tabs", () => {
  renderShell();
  for (const label of TAB_LABELS) {
    expect(screen.getByRole("link", { name: new RegExp(label, "i") })).toBeInTheDocument();
  }
});

test("tab links carry the current query so one click keeps the run (5.13)", () => {
  // the storyboard's one-click jumps only work if ?run= survives the switch; every
  // section reads what it needs and ignores the rest. Which section a tab lands on
  // is the shell's choice — that the query rides along is not
  renderShell("/strategy/replay?run=7");
  for (const label of TAB_LABELS) {
    const href = screen.getByRole("link", { name: new RegExp(label, "i") }).getAttribute("href");
    expect(href, label).toMatch(new RegExp(`^/${label}(/[a-z]+)?\\?run=7$`));
  }
});
