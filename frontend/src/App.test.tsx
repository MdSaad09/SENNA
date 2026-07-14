import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import App from "./App";

test("shows the SENNA title", () => {
  render(<App />);
  expect(screen.getByText("SENNA")).toBeInTheDocument();
});
