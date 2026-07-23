import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, test } from "vitest";

import App from "./App";

afterEach(cleanup);

// the shell needs a router for its NavLinks; MemoryRouter is the lightest one
function renderShell() {
  render(
    <MemoryRouter>
      <App />
    </MemoryRouter>,
  );
}

test("shows the SENNA title", () => {
  renderShell();
  expect(screen.getByText("SENNA")).toBeInTheDocument();
});

test("keeps the R-07 footer and offers all six views", () => {
  renderShell();
  expect(screen.getByText(/unofficial student project/i)).toBeInTheDocument();
  for (const label of ["circuit", "replay", "energy", "tyres", "live", "counterfactual"]) {
    expect(screen.getByRole("link", { name: label })).toBeInTheDocument();
  }
});
