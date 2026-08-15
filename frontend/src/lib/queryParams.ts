// One place that reads the URL. Four views used to do it themselves —
// runIdFromLocation byte-identical in RaceReplayView and EnergyView, and a second
// intParam/seedParam pair in LiveSimulationView and CounterfactualView — and they did
// not agree about what a bad value means. The demo deep link (5.13) carries the union of
// every section's params, so they all parse the same string.

import { useCallback } from "react";
import { useSearchParams } from "react-router-dom";

/** Views that read several params build the URLSearchParams once and pass it along. */
type Query = string | URLSearchParams;

const asParams = (query: Query) =>
  typeof query === "string" ? new URLSearchParams(query) : query;

/** A positive integer, or null. Rejects 0, negatives and anything non-numeric — a bad
 *  ?run= should show the picker, never fetch /v1/simulations/NaN. */
export function positiveIntParam(name: string, search: Query = window.location.search): number | null {
  const raw = asParams(search).get(name);
  if (raw === null || !/^\d+$/.test(raw)) return null;
  const value = Number(raw);
  return value > 0 ? value : null;
}

/** Seeds differ from run ids: 0 is a legitimate seed. */
export function seedParam(search: Query = window.location.search): number | null {
  const raw = asParams(search).get("seed");
  if (raw === null || !/^\d+$/.test(raw)) return null;
  return Number(raw);
}

/** Write the resolved run id back into the URL, through the router.
 *
 *  Every view that POSTs a run used to do this with `window.history.replaceState`, which
 *  react-router's data router never observes — so `useLocation().search` stayed on the
 *  pre-run query and every subsequent nav click, section-rail hop and 5.13 jump link
 *  handed on a URL with no `?run=`. The 1:15 beat landed on the energy view's own run
 *  picker instead of the SOC trajectory. The deep link stays shareable either way:
 *  circuit and seed are preserved, only `run` is added. */
export function useWriteRunBack(): (runId: number) => void {
  const [, setSearchParams] = useSearchParams();
  // stable, so the deep-link effects that call it can honour it as a dependency without
  // re-running on every render
  return useCallback(
    (runId: number) =>
      setSearchParams(
        (current) => {
          current.set("run", String(runId));
          return current;
        },
        { replace: true },
      ),
    [setSearchParams],
  );
}
