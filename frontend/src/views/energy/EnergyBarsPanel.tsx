// Harvest and deploy per lap, with the per-event harvest cap drawn as the only
// reference line (E-02). There is deliberately no line at 4 MJ: deployment routinely
// exceeds the store because the car harvests mid-lap, and the fictional deploy plane
// was removed in v3 (F-02, R-03). The harvest teal is reused from the circuit view so
// one colour means one thing across the dashboard.

import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { EnergyProfile } from "../../api/types";
import { HARVEST_TINT } from "../circuit/CircuitRibbon";
import { CHART } from "../../config/palette";

// stylised — deploy amber against the reused harvest teal
export const DEPLOY_TINT = CHART.deploy;

export default function EnergyBarsPanel({ profile }: { profile: EnergyProfile }) {
  // Every reference line goes through this one array, so the drawn chart and the
  // accessible list below it can never drift (the Legend-swatch discipline). It is
  // also the F-02 tripwire: a reintroduced 4 MJ deploy plane would have to appear here,
  // where the regression test counts the lines and reads their values.
  const referenceLines = [{ key: "harvest-cap", mj: profile.h_max_mj, label: "harvest cap" }];

  return (
    <figure
      data-testid="energy-bars"
      className="rounded border border-senna-line bg-senna-surface/40 p-3"
    >
      <figcaption className="text-xs text-senna-muted">
        harvest and deploy per lap — the dashed line is the harvest cap (E-02); deployment is
        bounded by SOC, not by any fixed ceiling (F-02).
      </figcaption>
      <div className="h-44">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={profile.laps} margin={{ top: 8, right: 12, bottom: 0, left: -16 }}>
            <CartesianGrid stroke={CHART.gridLine} />
            <XAxis dataKey="lap" stroke={CHART.axis} fontSize={11} />
            <YAxis stroke={CHART.axis} fontSize={11} />
            <Tooltip
              contentStyle={{
                background: CHART.tooltipBg,
                border: `1px solid ${CHART.tooltipLine}`,
                fontSize: 12,
              }}
              formatter={(value: number, name) => [`${value.toFixed(2)} MJ`, name]}
            />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="harvest_mj" name="harvest" fill={HARVEST_TINT} isAnimationActive={false} />
            <Bar dataKey="deploy_mj" name="deploy" fill={DEPLOY_TINT} isAnimationActive={false} />
            {referenceLines.map((line) => (
              <ReferenceLine
                key={line.key}
                y={line.mj}
                stroke={HARVEST_TINT}
                strokeDasharray="4 2"
                ifOverflow="extendDomain"
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
      {/* the same reference lines in readable form — recharts draws no SVG under jsdom,
          so this is where the F-02 test can see that the only line is the harvest cap */}
      <ul data-testid="bars-reference-lines" className="mt-1 text-xs text-senna-faint">
        {referenceLines.map((line) => (
          <li key={line.key} data-mj={line.mj}>
            {line.label} {line.mj} MJ per lap
          </li>
        ))}
      </ul>
    </figure>
  );
}
