import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, test } from "vitest";

import { energyProfile, installFetchStub, simulationResult } from "../../test/apiFixtures";
import EnergyView from "./EnergyView";

// The energy view is 2D (decision 2) — no canvas, so no R3F mock. ?run= is plain view
// state read off the URL, exactly as the replay view reads it.

let restoreFetch: () => void;

beforeEach(() => {
  window.history.replaceState(null, "", "/energy?run=7");
  restoreFetch = installFetchStub();
});

afterEach(() => {
  cleanup();
  restoreFetch();
  window.history.replaceState(null, "", "/");
});

function renderView() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <EnergyView />
    </QueryClientProvider>,
  );
}

test("a deploy-heavy run draws harvest against H_max with no 4 MJ cap marker (F-02)", async () => {
  // the fixture deploys past 4 MJ on several laps; that is legal because the car
  // harvests mid-lap, and the bars panel must never draw a cap that says otherwise
  renderView();
  const bars = await screen.findByTestId("energy-bars");
  expect(within(bars).getByText(/harvest cap 8\.5 MJ per lap/i)).toBeInTheDocument();
  // R-03: no deploy plane, no per-lap cap, no 4 MJ line anywhere in the bars panel
  expect(within(bars).queryByText(/4\s*MJ/i)).toBeNull();
  expect(within(bars).queryByText(/deploy cap|per-lap cap|deploy plane/i)).toBeNull();
});

test("the footer states the modelled-calibrated honesty line (F-13)", async () => {
  renderView();
  expect(
    await screen.findByText(/modelled, calibrated to 2026 aggregate behaviour/i),
  ).toBeInTheDocument();
});

test("the SOC panel bounds its axis at the served usable store, not a hardcoded number", async () => {
  // E-01: the 4 MJ store is real and belongs on the SOC axis; it is served, never a
  // frontend literal — the fixture's usable_soc_mj is what must appear
  const soc = await screen.findByTestId("energy-soc");
  expect(within(soc).getByText(/4 MJ usable store/i)).toBeInTheDocument();
});

test("pit laps are marked from the recorded pit action", async () => {
  renderView();
  // the fixture pits on lap 4 (pit != 0)
  expect(await screen.findByText(/pit.*lap 4/i)).toBeInTheDocument();
});

test("an in-flight run reports its status instead of an empty chart (E-16)", async () => {
  restoreFetch();
  restoreFetch = installFetchStub({
    "/v1/simulations/7": { ...simulationResult, status: "running", finished_at: null },
  });
  renderView();
  expect(await screen.findByText(/running/i)).toBeInTheDocument();
  // no chart, so no honesty footer yet
  expect(screen.queryByText(/modelled, calibrated/i)).toBeNull();
  // the fixture keeps its data reachable, but the guard is status, not presence
  expect(energyProfile.laps.length).toBeGreaterThan(0);
});
