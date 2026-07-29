// The agent's banked energy at the playhead — the 5.13 demo beat "watch the store
// fill before an attack". The scale is the run's served usable store (E-01): a
// client-side 4 MJ literal would lie about any run raced under a different store,
// so both the width and the printed ceiling come from the caller's EnergyProfile.

import { SOC_TINT } from "../energy/SocPanel";

export default function SocBar({ socMj, usableSocMj }: { socMj: number; usableSocMj: number }) {
  return (
    <div data-testid="soc-bar" className="rounded border border-neutral-800 p-2">
      <div className="flex items-baseline justify-between text-xs">
        <span className="text-neutral-500">state of charge</span>
        <span className="font-mono text-neutral-300">
          {socMj.toFixed(2)} / {usableSocMj} MJ
        </span>
      </div>
      <div className="mt-1.5 h-2 overflow-hidden rounded-sm bg-neutral-800">
        <div
          className="h-full rounded-sm"
          style={{ width: `${(socMj / usableSocMj) * 100}%`, backgroundColor: SOC_TINT }}
        />
      </div>
    </div>
  );
}
