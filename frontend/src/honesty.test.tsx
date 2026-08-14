// Spec 5.10.2 gives every view an honesty statement, and until F23 nothing failed
// when one went missing — a restyle could drop any of them silently. This file is the
// guard: one test per statement, each string pinned as it ships.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { ILLUSTRATIVE_MOTION_CAPTION } from "./components/TransportControls";
import { useLiveStore } from "./stores/liveStore";
import { installFetchStub } from "./test/apiFixtures";
import { installFakeWebSocket } from "./test/fakeSocket";
import CircuitExplorerView from "./views/circuit/CircuitExplorerView";
import CounterfactualView from "./views/counterfactual/CounterfactualView";
import EnergyView from "./views/energy/EnergyView";
import LiveSimulationView from "./views/live/LiveSimulationView";
import RaceReplayView from "./views/replay/RaceReplayView";
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
  render(<QueryClientProvider client={queryClient}>{view}</QueryClientProvider>);
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
