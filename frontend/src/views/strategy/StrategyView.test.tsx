import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, test } from "vitest";

import { installFetchStub, simulationResult, strategyFrames } from "../../test/apiFixtures";
import StrategyView from "./StrategyView";
import { BrowserRouter } from "react-router-dom";

// The Strategy page is post-hoc: run it, then show what the agent did. Every figure
// here is already served — worker/jobs.py:209-217 builds the summary, and the stints
// come from the frames. No backend change, and no number computed in the browser.
const egoFrames = strategyFrames(
  6,
  2,
  { startCompound: "MEDIUM", stops: [{ lap: 4, compound: "HARD" }] },
  22,
);

const completedRun = {
  ...simulationResult,
  config: { grid_position: 8 },
  summary: {
    nominal_lap_s: 90.0,
    final_position: 2,
    // real, but RL-scaled: terminal_points divides the FIA table by points_divisor
    // 2.5 (configs/env.yaml:22-23), so a P2 finish serves 7.2 rather than 18. Saad's
    // decision, 14 Aug 2026: the headline is position only, and this must not show
    points: 7.2,
    race_time_s: 5412.4,
    dnf: false,
    pit_laps: [4],
    compounds: ["MEDIUM", "HARD"],
    n_cars: 22,
    total_laps: 6,
  },
};

let restoreFetch: () => void;

function stubWith(run: Record<string, unknown>) {
  restoreFetch();
  // the frames key must come first: "/v1/simulations/7" alone would also swallow the
  // /7/frames request and feed it a run object
  restoreFetch = installFetchStub({
    "/v1/simulations/7/frames": egoFrames,
    "/v1/simulations/7": run,
  });
}

beforeEach(() => {
  window.history.replaceState(null, "", "/strategy/setup?run=7");
  restoreFetch = installFetchStub();
  stubWith(completedRun);
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
      {/* F23: ?run= and ?circuit= are written through the router now, not with a raw
          history.replaceState the router cannot see */}
      <BrowserRouter>
        <StrategyView />
      </BrowserRouter>
    </QueryClientProvider>,
  );
}

test("the headline reads the grid slot into the finishing position", async () => {
  renderView();
  const headline = await screen.findByTestId("strategy-headline");
  expect(headline).toHaveTextContent("P8"); // config.grid_position
  expect(headline).toHaveTextContent("P2"); // summary.final_position
  // 5412.4 s of served race time, as the clock the header prints
  expect(document.body.textContent).toContain("1:30:12");
});

test("no points appear anywhere, because the served figure is RL-scaled", async () => {
  renderView();
  await screen.findByTestId("strategy-headline");
  expect(screen.queryByText(/\bpoints\b|\bpts\b/i)).toBeNull();
  expect(document.body.textContent).not.toContain("7.2");
});

test("the pit table has exactly the four served columns", async () => {
  // guards against re-adding a service-time column: senna/env/engine.py:100 computes
  // pit_time_s, folds it into lap_time_s and never copies it into info, so no such
  // number is served and any figure in that column would be fabricated
  renderView();
  const schedule = await screen.findByTestId("pit-schedule");
  const headers = within(schedule).getAllByRole("columnheader").map((cell) => cell.textContent);

  expect(headers).toHaveLength(4);
  expect(headers[0]).toMatch(/stop|#/i);
  expect(headers[1]).toMatch(/from/i);
  expect(headers[2]).toMatch(/to/i);
  expect(headers[3]).toMatch(/lap/i);
  expect(schedule.textContent).not.toMatch(/service/i);
});

test("the pit table lists the one stop the run made", async () => {
  renderView();
  const schedule = await screen.findByTestId("pit-schedule");
  const stops = within(schedule).getAllByRole("row").slice(1); // drop the header row
  expect(stops).toHaveLength(1);
  expect(stops[0]).toHaveTextContent("MEDIUM");
  expect(stops[0]).toHaveTextContent("HARD");
  expect(stops[0]).toHaveTextContent("4");
});

test("a DNF run says DNF instead of a finishing position", async () => {
  stubWith({
    ...completedRun,
    summary: { ...completedRun.summary, dnf: true, final_position: 19 },
  });
  renderView();
  const headline = await screen.findByTestId("strategy-headline");
  expect(headline).toHaveTextContent("DNF");
  expect(headline.textContent).not.toMatch(/P19/);
});

test("a run still going shows its status, not an empty stint bar", async () => {
  stubWith({ ...completedRun, status: "running", finished_at: null, summary: null });
  renderView();
  expect((await screen.findAllByText(/running/i)).length).toBeGreaterThan(0);
  expect(screen.queryByTestId("stint-timeline")).toBeNull();
  expect(screen.queryByTestId("pit-schedule")).toBeNull();
});

test("the grid control offers 22 slots and cannot express 23", async () => {
  // sourced — SimulationCreate bounds, 5.9.2 (ge=1, le=22). The reference screenshot
  // runs its starting-position slider P1-P20; the 2026 grid is 22 cars, 11 teams.
  // A range input clamps rather than rejecting, which is the stronger guarantee: P23
  // is not a value the control can hold, so the server never sees it
  window.history.replaceState(null, "", "/strategy/setup");
  renderView();

  const gridPosition = (await screen.findByLabelText(/grid position/i)) as HTMLInputElement;
  expect(gridPosition).toHaveAttribute("min", "1");
  expect(gridPosition).toHaveAttribute("max", "22");

  fireEvent.change(gridPosition, { target: { value: "22" } });
  expect(gridPosition.value).toBe("22");
  fireEvent.change(gridPosition, { target: { value: "23" } });
  expect(gridPosition.value).toBe("22");
  expect(screen.getByTestId("grid-readout")).toHaveTextContent("P22");
});
