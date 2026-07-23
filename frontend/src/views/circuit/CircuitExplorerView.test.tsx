import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { installFetchStub } from "../../test/apiFixtures";
import CircuitExplorerView from "./CircuitExplorerView";

vi.mock("@react-three/fiber", async () => (await import("../../test/mockR3F")).fiberMock());
vi.mock("@react-three/drei", async () => (await import("../../test/mockR3F")).dreiMock());

let restoreFetch: () => void;

beforeEach(() => {
  restoreFetch = installFetchStub();
});

afterEach(() => {
  cleanup();
  restoreFetch();
});

function renderView() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <CircuitExplorerView />
    </QueryClientProvider>,
  );
}

test("the picker lists every circuit the API returns", async () => {
  renderView();
  expect(await screen.findByRole("button", { name: /bahrain/i })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /monaco/i })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /madrid/i })).toBeInTheDocument();
});

test("the legend caveats come from the detail flags, not hardcoded copy (5.10.2)", async () => {
  renderView();
  fireEvent.click(await screen.findByRole("button", { name: /bahrain/i }));

  // elevation and banking arrive flagged stylised in meta.json; X-mode sections
  // are inferred from telemetry; harvest has no real zone data (plan divergence 2)
  expect((await screen.findAllByText(/stylised/i)).length).toBeGreaterThan(0);
  expect((await screen.findAllByText(/inferred/i)).length).toBeGreaterThan(0);
  expect((await screen.findAllByText(/harvest/i)).length).toBeGreaterThan(0);
});

test("a circuit without a ribbon says so instead of crashing (F-08 coverage)", async () => {
  renderView();
  fireEvent.click(await screen.findByRole("button", { name: /madrid/i }));
  expect((await screen.findAllByText(/ribbon not built/i)).length).toBeGreaterThan(0);
});
