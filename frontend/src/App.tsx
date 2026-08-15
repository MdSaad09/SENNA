import { useEffect } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

import DevOverlay from "./components/DevOverlay";
import QualityToggle from "./components/QualityToggle";
import Segmented, { type Section } from "./components/ui/Segmented";
import { DEV_OVERLAY_KEY } from "./config/constants";
import { useUiStore } from "./stores/uiStore";

interface Tab {
  path: string;
  label: string;
  /** where the tab click lands; a tab with sections opens on its first one */
  home: string;
  sections: Section[];
}

// Three tabs, six spec views. 5.10.2 fixes the views and 5.10.3 allows one mounted
// canvas, so the views become sections on a rail rather than a flat nav or a scrolling
// page — a scroll layout would co-mount two canvases mid-scroll (F-28).
const TABS: Tab[] = [
  {
    path: "/strategy",
    label: "strategy",
    home: "/strategy/setup",
    sections: [
      { to: "/strategy/setup", label: "setup" },
      { to: "/strategy/replay", label: "replay" },
      { to: "/strategy/live", label: "live" },
    ],
  },
  { path: "/circuit", label: "circuit", home: "/circuit", sections: [] },
  {
    path: "/analysis",
    label: "analysis",
    home: "/analysis/energy",
    sections: [
      { to: "/analysis/energy", label: "energy" },
      { to: "/analysis/tyres", label: "tyres" },
      { to: "/analysis/decisions", label: "decisions" },
      { to: "/analysis/counterfactual", label: "counterfactual" },
    ],
  },
];

export default function App() {
  const toggleDevOverlay = useUiStore((state) => state.toggleDevOverlay);
  // the current query rides every switch (5.13): ?run= survives a click to the
  // counterfactual section, and each section reads what it needs and ignores the rest
  const { pathname, search } = useLocation();

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== DEV_OVERLAY_KEY) return;
      // typing in a form control, not toggling
      if ((event.target as HTMLElement).closest?.("input, select, textarea") != null) return;
      toggleDevOverlay();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [toggleDevOverlay]);

  const active = TABS.find((tab) => pathname.startsWith(tab.path));

  return (
    <div className="flex h-screen flex-col bg-senna-ground text-senna-muted">
      <header className="flex items-center gap-5 border-b border-senna-line bg-senna-ground px-5 py-3">
        <h1 className="text-base tracking-[0.42em] text-senna-accent">SENNA</h1>
        <p className="hidden border-l border-senna-line pl-5 text-micro uppercase leading-4 text-senna-ghost sm:block">
          Formula 1 strategy engine
          <br />
          2026 regulations · reinforcement learning
        </p>
        <div className="ml-auto">
          <QualityToggle />
        </div>
      </header>

      <nav className="flex gap-7 border-b border-senna-line px-5">
        {TABS.map((tab, index) => (
          <NavLink
            key={tab.path}
            to={{ pathname: tab.home, search }}
            className={() =>
              `-mb-px border-b-2 py-2.5 text-label uppercase tracking-[0.12em] ${
                tab === active
                  ? "border-senna-accent text-senna-text"
                  : "border-transparent text-senna-faint hover:text-senna-muted"
              }`
            }
          >
            <span className="text-senna-ghost">{String(index + 1).padStart(2, "0")}</span>{" "}
            &middot; {tab.label}
          </NavLink>
        ))}
      </nav>

      {active !== undefined && active.sections.length > 0 && (
        <Segmented sections={active.sections} search={search} />
      )}

      <main className="min-h-0 flex-1">
        <Outlet />
      </main>

      {/* R-07: the unofficial-project footer stays on every view. The wording is the
          canonical F15 disclaimer — it also fronts the README and the video end card,
          and the three may never drift apart */}
      <footer className="border-t border-senna-line px-5 py-1.5 text-[10px] text-senna-ghost">
        SENNA is an unofficial project and is not associated in any way with the Formula 1
        companies, the FIA or any team
      </footer>

      <DevOverlay />
    </div>
  );
}
