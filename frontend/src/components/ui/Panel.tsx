// The panel shape the reference repeats everywhere: hairline box, a header strip with a
// mint tick, an optional right-hand slot for a figure. Before F23 this classString was
// pasted into Legend, FitPanel, SocPanel and EnergyBarsPanel at two different background
// opacities for no reason anyone recorded.

import type { ReactNode } from "react";

interface PanelProps {
  children: ReactNode;
  className?: string;
}

export function Panel({ children, className = "" }: PanelProps) {
  return (
    <div className={`rounded-panel border border-senna-line bg-senna-surface ${className}`}>
      {children}
    </div>
  );
}

interface PanelHeaderProps {
  title: string;
  right?: ReactNode;
}

export function PanelHeader({ title, right }: PanelHeaderProps) {
  return (
    <div className="flex items-center gap-2 border-b border-senna-line bg-senna-raised px-3 py-2">
      <span aria-hidden className="h-3 w-[3px] shrink-0 bg-senna-accent" />
      <h2 className="text-micro uppercase text-senna-muted">{title}</h2>
      {right !== undefined && <div className="ml-auto text-label text-senna-faint">{right}</div>}
    </div>
  );
}
