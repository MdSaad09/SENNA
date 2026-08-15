// The reference's stint bar. Widths are lap counts, so a long middle stint looks long —
// the bar is a picture of the race's shape, not a decoration.

import { COMPOUND_COLOURS } from "../../config/palette";
import type { Stint } from "./stints";

const UNKNOWN_COMPOUND = "#515c63"; // stylised — a compound the palette has no hue for

export default function StintTimeline({ stints }: { stints: Stint[] }) {
  const totalLaps = stints.reduce((total, stint) => total + stint.laps, 0);
  if (totalLaps === 0) return null;

  return (
    <div data-testid="stint-timeline">
      <div className="flex h-9 w-full overflow-hidden rounded-panel">
        {stints.map((stint) => (
          <div
            key={stint.startLap}
            className="flex min-w-0 items-center justify-center border-r border-senna-ground last:border-r-0"
            style={{
              width: `${(stint.laps / totalLaps) * 100}%`,
              backgroundColor: COMPOUND_COLOURS[stint.compound] ?? UNKNOWN_COMPOUND,
            }}
            title={`${stint.compound}, laps ${stint.startLap}-${stint.endLap}`}
          >
            <span className="truncate px-1 text-micro uppercase text-senna-ground">
              {stint.compound.charAt(0)} {stint.laps}L
            </span>
          </div>
        ))}
      </div>

      <div className="mt-1 flex justify-between text-micro text-senna-ghost">
        <span>1</span>
        <span>{totalLaps}</span>
      </div>
    </div>
  );
}
