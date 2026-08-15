// Views are routes and navigation unmounts (F-28): each canvas section owns its
// CanvasHost, the shell owns none, so at most one canvas can exist and React swaps route
// elements in a single commit. F23 nests the eight sections under three tabs; the six
// pre-F23 paths stay reachable as redirects, because the demo deep links, the README and
// the e2e spec all point at them and a dead URL in a dissertation is a bad look.
//
// Imports are eager, deviating from the F11 plan's "lazy view imports": the router's lazy
// path builds an undici Request that jsdom's AbortSignal cannot satisfy, and this
// single-page dashboard ships every view to every visitor anyway.

import { type RouteObject } from "react-router-dom";

import App from "./App";
import KeepQuery from "./components/KeepQuery";
import DecisionsView from "./views/analysis/DecisionsView";
import CircuitExplorerView from "./views/circuit/CircuitExplorerView";
import CounterfactualView from "./views/counterfactual/CounterfactualView";
import EnergyView from "./views/energy/EnergyView";
import LiveSimulationView from "./views/live/LiveSimulationView";
import RaceReplayView from "./views/replay/RaceReplayView";
import StrategyView from "./views/strategy/StrategyView";
import TyreSurfaceView from "./views/tyres/TyreSurfaceView";

export const routes: RouteObject[] = [
  {
    path: "/",
    element: <App />,
    children: [
      { index: true, element: <KeepQuery to="/strategy/setup" /> },

      { path: "strategy/setup", element: <StrategyView /> },
      { path: "strategy/replay", element: <RaceReplayView /> },
      { path: "strategy/live", element: <LiveSimulationView /> },
      { path: "circuit", element: <CircuitExplorerView /> },
      { path: "analysis/energy", element: <EnergyView /> },
      { path: "analysis/tyres", element: <TyreSurfaceView /> },
      { path: "analysis/decisions", element: <DecisionsView /> },
      { path: "analysis/counterfactual", element: <CounterfactualView /> },

      { path: "strategy", element: <KeepQuery to="/strategy/setup" /> },
      { path: "analysis", element: <KeepQuery to="/analysis/energy" /> },

      { path: "replay", element: <KeepQuery to="/strategy/replay" /> },
      { path: "live", element: <KeepQuery to="/strategy/live" /> },
      { path: "energy", element: <KeepQuery to="/analysis/energy" /> },
      { path: "tyres", element: <KeepQuery to="/analysis/tyres" /> },
      { path: "counterfactual", element: <KeepQuery to="/analysis/counterfactual" /> },

      // an old bookmark or a typo lands inside the shell, not on react-router's bare
      // error page, which would ship without the R-07 footer (spec: every view)
      { path: "*", element: <KeepQuery to="/strategy/setup" /> },
    ],
  },
];
