// Views are routes and navigation unmounts (F-28): each canvas view owns its
// CanvasHost, the shell owns none, so at most one canvas can exist and React
// swaps route elements in a single commit. All six paths live here from F11 so
// the one-canvas rule is testable across the whole map; 3-6 are stubs.

import { Navigate, type RouteObject } from "react-router-dom";

import App from "./App";
import CircuitExplorerView from "./views/circuit/CircuitExplorerView";
import RaceReplayView from "./views/replay/RaceReplayView";
import StubView from "./views/StubView";

export const routes: RouteObject[] = [
  {
    path: "/",
    element: <App />,
    children: [
      { index: true, element: <Navigate to="/circuit" replace /> },
      { path: "circuit", element: <CircuitExplorerView /> },
      { path: "replay", element: <RaceReplayView /> },
      { path: "energy", element: <StubView title="Energy" arrives="F12" /> },
      { path: "tyres", element: <StubView title="Tyre Surface" arrives="F12" /> },
      { path: "live", element: <StubView title="Live Simulation" arrives="F13" /> },
      { path: "counterfactual", element: <StubView title="Counterfactual" arrives="F13" /> },
    ],
  },
];
