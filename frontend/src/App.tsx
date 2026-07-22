import { useEffect } from "react";
import { NavLink, Outlet } from "react-router-dom";

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
              to={view.path}
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

      {/* R-07: the unofficial-project footer stays on every view */}
      <footer className="border-t border-neutral-800 px-5 py-1.5 text-xs text-neutral-600">
        Unofficial student project — not affiliated with F1, the FIA or any team
      </footer>

      <DevOverlay />
    </div>
  );
}
