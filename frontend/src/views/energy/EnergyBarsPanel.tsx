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

// stylised — deploy amber against the reused harvest teal
export const DEPLOY_TINT = "#f97316";

export default function EnergyBarsPanel({ profile }: { profile: EnergyProfile }) {
  return (
    <figure
      data-testid="energy-bars"
      className="rounded border border-neutral-800 bg-neutral-900/40 p-3"
    >
      <figcaption className="text-xs text-neutral-300">
        harvest and deploy per lap — harvest cap {profile.h_max_mj} MJ per lap (E-02).
        Deployment is bounded by SOC, not by any fixed ceiling (F-02).
      </figcaption>
      <div className="h-44">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={profile.laps} margin={{ top: 8, right: 12, bottom: 0, left: -16 }}>
            <CartesianGrid stroke="#262626" />
            <XAxis dataKey="lap" stroke="#737373" fontSize={11} />
            <YAxis stroke="#737373" fontSize={11} />
            <Tooltip
              contentStyle={{ background: "#171717", border: "1px solid #404040", fontSize: 12 }}
              formatter={(value: number, name) => [`${value.toFixed(2)} MJ`, name]}
            />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="harvest_mj" name="harvest" fill={HARVEST_TINT} isAnimationActive={false} />
            <Bar dataKey="deploy_mj" name="deploy" fill={DEPLOY_TINT} isAnimationActive={false} />
            <ReferenceLine
              y={profile.h_max_mj}
              stroke={HARVEST_TINT}
              strokeDasharray="4 2"
              ifOverflow="extendDomain"
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </figure>
  );
}
