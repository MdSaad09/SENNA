// SOC over laps, bounded by the served usable store (E-01): the axis top is the 4 MJ
// store the run was raced under, not a frontend literal. Pit laps mark the trace from
// the recorded pit action so a stint's energy story lines up with its strategy.

import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { EnergyLap, EnergyProfile } from "../../api/types";
import { MODE_ACTION_LABELS } from "../../config/constants";
import { CHART } from "../../config/palette";

// stylised — SOC ribbon sky-blue; pit marks a muted grey so they read as annotation
export const SOC_TINT = CHART.soc;
export const PIT_MARK_TINT = CHART.pitMark;

// the 5.13 hover beat reads "banked energy before an attack" off this chart, and the
// SOC number alone cannot say that — the tooltip names the served mode next to it
export function socTooltip(lap: EnergyLap): string {
  return `${lap.soc_mj.toFixed(2)} MJ — ${MODE_ACTION_LABELS[lap.mode]}`;
}

export default function SocPanel({ profile }: { profile: EnergyProfile }) {
  const pitLaps = profile.laps.filter((lap) => lap.pit !== 0).map((lap) => lap.lap);

  return (
    <figure
      data-testid="energy-soc"
      className="rounded border border-senna-line bg-senna-surface/40 p-3"
    >
      <figcaption className="text-xs text-senna-muted">
        state of charge — {profile.usable_soc_mj} MJ usable store, the ledger never leaves [0,{" "}
        {profile.usable_soc_mj}] (E-01)
      </figcaption>
      <div className="h-44">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={profile.laps} margin={{ top: 8, right: 12, bottom: 0, left: -16 }}>
            <CartesianGrid stroke={CHART.gridLine} />
            <XAxis dataKey="lap" stroke={CHART.axis} fontSize={11} />
            <YAxis domain={[0, profile.usable_soc_mj]} stroke={CHART.axis} fontSize={11} />
            <Tooltip
              contentStyle={{
                background: CHART.tooltipBg,
                border: `1px solid ${CHART.tooltipLine}`,
                fontSize: 12,
              }}
              // the hovered point is one of profile.laps, so item.payload is that lap
              formatter={(_soc: number, _name, item) => [socTooltip(item.payload as EnergyLap), "SOC"]}
            />
            <Area
              type="monotone"
              dataKey="soc_mj"
              stroke={SOC_TINT}
              fill={SOC_TINT}
              fillOpacity={0.25}
              isAnimationActive={false}
            />
            {pitLaps.map((lap) => (
              <ReferenceLine key={lap} x={lap} stroke={PIT_MARK_TINT} strokeDasharray="3 3" />
            ))}
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <p className="mt-1 text-xs text-senna-faint">
        {pitLaps.length > 0
          ? `pit stops: ${pitLaps.map((lap) => `lap ${lap}`).join(", ")}`
          : "pit stops: none this run"}
      </p>
    </figure>
  );
}
