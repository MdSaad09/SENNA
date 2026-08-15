// Reading the URL was reimplemented in four views: runIdFromLocation byte-identical in
// RaceReplayView and EnergyView, and a second pair of intParam/seedParam helpers in
// LiveSimulationView and CounterfactualView. The demo deep link (5.13) carries the union
// of every section's params, so all of them parse the same string and they should agree
// about what a bad value means.

/** A positive integer, or null. Rejects 0, negatives and anything non-numeric — a bad
 *  ?run= should show the picker, never fetch /v1/simulations/NaN. */
export function positiveIntParam(name: string, search = window.location.search): number | null {
  const raw = new URLSearchParams(search).get(name);
  if (raw === null || !/^\d+$/.test(raw)) return null;
  const value = Number(raw);
  return value > 0 ? value : null;
}

/** Seeds differ from run ids: 0 is a legitimate seed. */
export function seedParam(search = window.location.search): number | null {
  const raw = new URLSearchParams(search).get("seed");
  if (raw === null || !/^\d+$/.test(raw)) return null;
  return Number(raw);
}

export function stringParam(name: string, search = window.location.search): string | null {
  const raw = new URLSearchParams(search).get(name);
  return raw === null || raw === "" ? null : raw;
}
