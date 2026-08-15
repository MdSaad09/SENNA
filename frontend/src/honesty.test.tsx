// Spec 5.10.2 gives every view an honesty statement, and until F23 nothing failed
// when one went missing — a restyle could drop any of them silently. This file is the
// guard: one test per statement, each string pinned as it ships.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { BrowserRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { ILLUSTRATIVE_MOTION_CAPTION } from "./components/TransportControls";
import { useLiveStore } from "./stores/liveStore";
import {
  decisionCardPitLap,
  installFetchStub,
  simulationResult,
  strategyFrames,
} from "./test/apiFixtures";
import { installFakeWebSocket } from "./test/fakeSocket";
import CircuitExplorerView from "./views/circuit/CircuitExplorerView";
import CounterfactualView from "./views/counterfactual/CounterfactualView";
import EnergyView from "./views/energy/EnergyView";
import LiveSimulationView from "./views/live/LiveSimulationView";
import RaceReplayView from "./views/replay/RaceReplayView";
import DecisionsView from "./views/analysis/DecisionsView";
import StrategyView from "./views/strategy/StrategyView";
import TyreSurfaceView from "./views/tyres/TyreSurfaceView";

vi.mock("@react-three/fiber", async () => (await import("./test/mockR3F")).fiberMock());
vi.mock("@react-three/drei", async () => (await import("./test/mockR3F")).dreiMock());

let restoreFetch: () => void;
let restoreSocket: () => void;

beforeEach(() => {
  useLiveStore.getState().reset();
  restoreFetch = installFetchStub();
  restoreSocket = installFakeWebSocket();
});

afterEach(() => {
  cleanup();
  restoreFetch();
  restoreSocket();
  window.history.replaceState(null, "", "/");
});

function renderAt(path: string, view: ReactElement) {
  window.history.replaceState(null, "", path);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  // BrowserRouter reads the path just set: the sections write ?run= back through the
  // router now, and several of them render 5.13 jump links
  render(
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>{view}</BrowserRouter>
    </QueryClientProvider>,
  );
}

test("the energy section states the series are modelled, not telemetry (F-13)", async () => {
  renderAt("/analysis/energy?run=7", <EnergyView />);
  expect(
    await screen.findByText("modelled, calibrated to 2026 aggregate behaviour"),
  ).toBeInTheDocument();
});

test("the counterfactual section states it is an in-simulator comparison (F-24)", async () => {
  renderAt("/analysis/counterfactual?run=41", <CounterfactualView />);
  expect(
    await screen.findByText("in-simulator comparison under stated assumptions"),
  ).toBeInTheDocument();
});

test("the live section states the agent races in the simulator, not live timing (R-05)", async () => {
  renderAt("/strategy/live?run=7", <LiveSimulationView />);
  expect(
    await screen.findByText(
      "live simulation — the trained agent racing in the simulator, not live timing",
    ),
  ).toBeInTheDocument();
});

test("the replay transport carries the illustrative-motion caption (5.10.2 row 2)", async () => {
  // imported rather than retyped: the caption is exported so both replay-shaped views
  // state it verbatim, and a copy here would let the two drift
  renderAt("/strategy/replay?run=7", <RaceReplayView />);
  expect(await screen.findByText(ILLUSTRATIVE_MOTION_CAPTION)).toBeInTheDocument();
});

test("the tyre surface labels its temperature axis as stylised, not fitted", async () => {
  renderAt("/analysis/tyres", <TyreSurfaceView />);
  expect(
    await screen.findByText(
      "temperature response — stylised illustration, not fitted, not a prediction; the T5 fit is age-only",
    ),
  ).toBeInTheDocument();
});

test("the circuit legend keeps all five caveats (5.10.2 row 1)", async () => {
  renderAt("/circuit", <CircuitExplorerView />);
  fireEvent.click(await screen.findByRole("button", { name: /bahrain/i }));

  // the wording is driven by the meta.json flags the fixture serves: elevation and
  // banking stylised, X-mode inferred, harvest with no official zone data
  expect(
    await screen.findByText("braking zones — inferred from telemetry speed drops"),
  ).toBeInTheDocument();
  expect(
    screen.getByText(
      "harvest shown at braking zones — stylised; no official zone data, H_max 8.5 MJ per lap applies circuit-wide",
    ),
  ).toBeInTheDocument();
  expect(
    screen.getByText(
      "X-mode sections — stylised, inferred from full-throttle stretches, not official section data",
    ),
  ).toBeInTheDocument();
  expect(screen.getByText("elevation stylised — smoothed Z, exaggerated 1.5x")).toBeInTheDocument();
  expect(
    screen.getByText("banking stylised — a visual treatment, not data (F-12)"),
  ).toBeInTheDocument();
});

// The two sections F23 added carry their own statements. They were not covered when this
// file was first written, which is exactly the hole it exists to close — a restyle could
// drop them and nothing would fail.

const completedRun = {
  ...simulationResult,
  status: "complete",
  config: { grid_position: 8 },
  summary: { final_position: 2, race_time_s: 5412.4, dnf: false, total_laps: 6 },
};

function stubCompletedRun(extra: Record<string, unknown> = {}) {
  restoreFetch();
  // the specific keys must precede the bare run: "/v1/simulations/7" alone also matches
  // the /frames and /decisions URLs and would feed them a run object
  restoreFetch = installFetchStub({
    "/v1/simulations/7/frames": strategyFrames(
      6,
      2,
      { startCompound: "MEDIUM", stops: [{ lap: 4, compound: "HARD" }] },
      22,
    ),
    ...extra,
    "/v1/simulations/7": completedRun,
  });
}

test("the strategy section states the stints are read back, not planned", async () => {
  stubCompletedRun();
  renderAt("/strategy/setup?run=7", <StrategyView />);
  expect(
    await screen.findByText(/there is no plan here that preceded the race/i),
  ).toBeInTheDocument();
  // and the reason the pit table has four columns and not five
  expect(screen.getByText(/service time is not shown because it is not served/i)).toBeVisible();
});

test("the reward panel states it shows every served term and no others", async () => {
  // decisionCardPitLap is lap 14, and the panel reads that lap's reward_terms out of the
  // frames — so the run has to be long enough to contain it
  stubCompletedRun({
    "/v1/simulations/7/decisions": [decisionCardPitLap],
    "/v1/simulations/7/frames": strategyFrames(
      20,
      2,
      { startCompound: "MEDIUM", stops: [{ lap: 12, compound: "HARD" }] },
      22,
    ),
  });
  renderAt("/analysis/decisions?run=7", <DecisionsView />);
  expect(
    await screen.findByText(/every term the environment served for this lap, and no others/i),
  ).toBeInTheDocument();
});

test("the alternatives panel states it is one lap's policy, not a search over strategies", async () => {
  stubCompletedRun({ "/v1/simulations/7/decisions": [decisionCardPitLap] });
  renderAt("/analysis/decisions?run=7", <DecisionsView />);
  expect(
    await screen.findByText(/not a search over whole\s+strategies/i),
  ).toBeInTheDocument();
  // compliance is by construction, never by a reward penalty (F-16)
  expect(screen.getByText(/forbidden by the action mask/i)).toBeVisible();
});

test("a run with no stored explanations says so rather than explaining a ghost (E-15)", async () => {
  stubCompletedRun({ "/v1/simulations/7/decisions": [] });
  renderAt("/analysis/decisions?run=7", <DecisionsView />);
  expect(await screen.findByText(/no stored explanations for model version/i)).toBeInTheDocument();
});
