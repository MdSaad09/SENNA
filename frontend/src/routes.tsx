// Views are routes and navigation unmounts (F-28): each canvas view owns its
// CanvasHost, the shell owns none, so at most one canvas can exist and React
// swaps route elements in a single commit. All six paths live here from F11 so
// the one-canvas rule is testable across the whole map; 3-6 are stubs.
//
// Imports are eager, deviating from the plan's "lazy view imports": the router's
// lazy path builds an undici Request that jsdom's AbortSignal cannot satisfy, and
// this single-page dashboard ships every view to every visitor anyway.

import { Navigate, type RouteObject } from "react-router-dom";

import App from "./App";
import CircuitExplorerView from "./views/circuit/CircuitExplorerView";
import CounterfactualView from "./views/counterfactual/CounterfactualView";
import EnergyView from "./views/energy/EnergyView";
import LiveSimulationView from "./views/live/LiveSimulationView";
import RaceReplayView from "./views/replay/RaceReplayView";
import TyreSurfaceView from "./views/tyres/TyreSurfaceView";

export const routes: RouteObject[] = [
  {
    path: "/",
    element: <App />,
    children: [
      { index: true, element: <Navigate to="/circuit" replace /> },
      { path: "circuit", element: <CircuitExplorerView /> },
      { path: "replay", element: <RaceReplayView /> },
      { path: "energy", element: <EnergyView /> },
      { path: "tyres", element: <TyreSurfaceView /> },
      { path: "live", element: <LiveSimulationView /> },
      { path: "counterfactual", element: <CounterfactualView /> },
    ],
  },
];
