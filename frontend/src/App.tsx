import { useEffect } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

import DevOverlay from "./components/DevOverlay";
import QualityToggle from "./components/QualityToggle";
import { DEV_OVERLAY_KEY } from "./config/constants";
import { useUiStore } from "./stores/uiStore";

const VIEWS = [
  { path: "/circuit", label: "circuit" },
  { path: "/replay", label: "replay" },
  { path: "/energy", label: "energy" },
  { path: "/tyres", label: "tyres" },
  { path: "/live", label: "live" },
  { path: "/counterfactual", label: "counterfactual" },
];

export default function App() {
  const toggleDevOverlay = useUiStore((state) => state.toggleDevOverlay);
  // the current query rides every view switch (5.13): ?run= survives one click to
  // the counterfactual view, and each view reads what it needs and ignores the rest
  const { search } = useLocation();

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

  return (
    <div className="flex h-screen flex-col bg-neutral-950 text-neutral-100">
      <header className="flex items-center gap-6 border-b border-neutral-800 px-5 py-2.5">
        <h1 className="text-base font-semibold tracking-[0.3em]">SENNA</h1>
        <nav className="flex gap-1 text-sm">
          {VIEWS.map((view) => (
            <NavLink
              key={view.path}
              to={{ pathname: view.path, search }}
              className={({ isActive }) =>
                `rounded px-2.5 py-1 ${
                  isActive
                    ? "bg-neutral-800 text-neutral-100"
                    : "text-neutral-400 hover:text-neutral-200"
                }`
              }
            >
              {view.label}
            </NavLink>
          ))}
        </nav>
        <div className="ml-auto">
          <QualityToggle />
        </div>
      </header>

      <main className="min-h-0 flex-1">
        <Outlet />
      </main>

      {/* R-07: the unofficial-project footer stays on every view. The wording is the
          canonical F15 disclaimer — it also fronts the README and the video end
          card, and the three may never drift apart */}
      <footer className="border-t border-neutral-800 px-5 py-1.5 text-xs text-neutral-600">
        SENNA is an unofficial project and is not associated in any way with the Formula 1
        companies, the FIA or any team
      </footer>

      <DevOverlay />
    </div>
  );
}
