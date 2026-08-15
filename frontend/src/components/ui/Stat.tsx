// A labelled figure, and a labelled figure with a bar under it. The bar earns its own
// component because the reward decomposition and the circuit characteristics rail both
// draw one and neither should own the fill arithmetic.

import type { ReactNode } from "react";

import { MicroLabel } from "./text";

interface StatProps {
  label: string;
  value: ReactNode;
  className?: string;
}

export function Stat({ label, value, className = "" }: StatProps) {
  return (
    <div className={className}>
      <MicroLabel>{label}</MicroLabel>
      <p className="text-figure text-senna-text">{value}</p>
    </div>
  );
}

interface MeterProps {
  label: string;
  value: ReactNode;
  /** 0-1; clamped, because a served ratio outside the range is data to show, not to crash on */
  fill: number;
  tint?: string;
}

export function Meter({ label, value, fill, tint }: MeterProps) {
  const width = `${Math.min(Math.max(fill, 0), 1) * 100}%`;
  return (
    <div className="py-1.5">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-label uppercase text-senna-muted">{label}</span>
        <span className="text-label text-senna-text">{value}</span>
      </div>
      <div className="mt-1 h-px w-full bg-senna-line">
        <div
          className="h-px bg-senna-accent"
          style={{ width, ...(tint === undefined ? {} : { backgroundColor: tint }) }}
        />
      </div>
    </div>
  );
}
