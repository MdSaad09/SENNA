// Every stylised or inferred element on the canvas is named here, with the wording
// driven by the meta.json flags the API passes through — honesty rendered from
// data, not hardcoded copy (5.10.2 row 1).

import type { CircuitDetail } from "../../api/types";

function Swatch({ colour }: { colour: string }) {
  return (
    <span
      className="mr-2 inline-block h-2.5 w-2.5 rounded-sm align-middle"
      style={{ backgroundColor: colour }}
    />
  );
}

function elevationCaveat(detail: CircuitDetail): string {
  const flags = detail.flags;
  if (flags === null) return "elevation unknown";
  if (flags.source === "flat_plus_camber") {
    const camber = flags.camber_deg !== undefined ? ` with ${flags.camber_deg} deg camber` : "";
    return `elevation ${flags.elevation ?? "stylised"} — no Z data, rendered flat${camber}`;
  }
  return `elevation ${flags.elevation ?? "stylised"} — smoothed Z, exaggerated 1.5x`;
}

export default function Legend({ detail }: { detail: CircuitDetail }) {
  const flags = detail.flags;
  return (
    <aside className="rounded border border-neutral-800 bg-neutral-900/80 p-3 text-xs text-neutral-300">
      <h3 className="font-semibold text-neutral-200">
        {detail.id.replace(/_/g, " ")} — {detail.race_laps} laps
        {detail.lap_length_m !== null && `, ${(detail.lap_length_m / 1000).toFixed(3)} km`}
      </h3>
      <ul className="mt-2 space-y-1">
        <li>
          <Swatch colour="#d97706" />
          braking zones — inferred from telemetry speed drops
        </li>
        <li>
          <Swatch colour="#0d9488" />
          harvest shown at braking zones — stylised; no official zone data, H_max{" "}
          {detail.h_max_mj} MJ per lap applies circuit-wide
        </li>
        <li>
          <Swatch colour="#7c3aed" />
          X-mode sections — {flags?.xmode ?? "stylised"}, inferred from full-throttle
          stretches, not official section data
        </li>
        <li>{elevationCaveat(detail)}</li>
        <li>banking {flags?.banking ?? "stylised"} — a visual treatment, not data (F-12)</li>
      </ul>
    </aside>
  );
}
