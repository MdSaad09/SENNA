// Four columns, and deliberately not five. The reference shows a SERVICE column reading
// 2.4s; senna/env/engine.py:100 computes pit_time_s, folds it into the lap time and never
// copies it into info, so no such figure is served. StrategyView.test.tsx pins the column
// set so nobody fills that gap with a plausible number.

import { COMPOUND_COLOURS } from "../../config/palette";
import type { Stint } from "./stints";

function CompoundCell({ compound }: { compound: string }) {
  return (
    <span className="flex items-center gap-2">
      <span
        aria-hidden
        className="h-2 w-2 shrink-0"
        style={{ backgroundColor: COMPOUND_COLOURS[compound] ?? "transparent" }}
      />
      {compound}
    </span>
  );
}

export default function PitSchedule({ stints }: { stints: Stint[] }) {
  const stops = stints.slice(1);

  if (stops.length === 0) {
    return (
      <p data-testid="pit-schedule" className="px-3 py-3 text-label text-senna-faint">
        no stops — the agent ran the whole race on one set
      </p>
    );
  }

  return (
    <table data-testid="pit-schedule" className="w-full text-label">
      <thead>
        <tr className="border-b border-senna-line text-micro uppercase text-senna-faint">
          <th scope="col" className="px-3 py-2 text-left font-normal">
            Stop
          </th>
          <th scope="col" className="px-3 py-2 text-left font-normal">
            From
          </th>
          <th scope="col" className="px-3 py-2 text-left font-normal">
            To
          </th>
          <th scope="col" className="px-3 py-2 text-right font-normal">
            Lap
          </th>
        </tr>
      </thead>
      <tbody>
        {stops.map((stint, index) => (
          <tr key={stint.startLap} className="border-b border-senna-line/60 last:border-b-0">
            <td className="px-3 py-2 text-senna-faint">#{index + 1}</td>
            <td className="px-3 py-2 text-senna-muted">
              <CompoundCell compound={stints[index].compound} />
            </td>
            <td className="px-3 py-2 text-senna-muted">
              <CompoundCell compound={stint.compound} />
            </td>
            <td className="px-3 py-2 text-right text-senna-text">{stint.startLap}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
