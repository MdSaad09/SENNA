// The position-delta chart: baseline minus agent per lap, positive = the agent runs
// ahead of the real strategy. recharts SVG per the energy-view discipline, with the
// reference lines and every row mirrored into an accessible list — jsdom sees no
// SVG paths, so the mirror is what the tests (and screen readers) read.

import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useEffect, useState } from "react";

import { EGO_ACCENT } from "../../config/liveries";
import { useReplayStore } from "../../stores/replayStore";
import type { DeltaPoint } from "../../lib/divergence";
import { CHART } from "../../config/palette";

interface DeltaChartPanelProps {
  series: DeltaPoint[];
  divergenceLap: number | null;
  baselineEndsLap: number | null; // set when the baseline race is the shorter one
}

export default function DeltaChartPanel({
  series,
  divergenceLap,
  baselineEndsLap,
}: DeltaChartPanelProps) {
  // once per lap, not per frame — the lap-gating trick from the transport controls
  const [cursorLap, setCursorLap] = useState(1);
  useEffect(() => {
    let shown = 0;
    return useReplayStore.subscribe(
      (state) => state.playheadLap,
      (playheadLap) => {
        const lap = Math.max(1, Math.ceil(playheadLap));
        if (lap !== shown) {
          shown = lap;
          setCursorLap(lap);
        }
      },
    );
  }, []);

  const lastLap = series.length === 0 ? 1 : series[series.length - 1].lap;

  return (
    <section className="border-t border-senna-line px-4 py-2">
      <div className="flex items-baseline gap-4 text-xs text-senna-faint">
        <h2 className="font-semibold text-senna-text">position delta</h2>
        <span>baseline minus SENNA per lap — positive means the strategy gains places</span>
        {divergenceLap !== null && (
          <span className="text-senna-muted">strategies diverge on lap {divergenceLap}</span>
        )}
        {baselineEndsLap !== null && (
          <span>baseline ends on lap {baselineEndsLap} — the chart stops there</span>
        )}
      </div>

      <div className="h-40">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={series} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
            <CartesianGrid stroke={CHART.gridLine} strokeDasharray="3 3" />
            <XAxis dataKey="lap" stroke={CHART.axis} fontSize={11} />
            <YAxis stroke={CHART.axis} fontSize={11} allowDecimals={false} />
            <Tooltip
              isAnimationActive={false}
              contentStyle={{ backgroundColor: CHART.tooltipBg, border: `1px solid ${CHART.tooltipLine}` }}
            />
            <ReferenceLine y={0} stroke={CHART.axis} />
            {divergenceLap !== null && (
              <ReferenceLine x={divergenceLap} stroke={CHART.divergence} strokeDasharray="4 2" />
            )}
            <ReferenceLine x={Math.min(cursorLap, lastLap)} stroke={CHART.cursor} />
            <Line
              type="stepAfter"
              dataKey="delta"
              stroke={EGO_ACCENT}
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <ul data-testid="delta-mirror" className="sr-only">
        {series.map((point) => (
          <li key={point.lap} data-lap={point.lap} data-delta={point.delta}>
            lap {point.lap}: {point.delta >= 0 ? `+${point.delta}` : point.delta}
          </li>
        ))}
      </ul>
    </section>
  );
}
