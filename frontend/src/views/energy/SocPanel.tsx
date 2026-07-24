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

import type { EnergyProfile } from "../../api/types";

// stylised — SOC ribbon sky-blue; pit marks a muted grey so they read as annotation
export const SOC_TINT = "#38bdf8";
export const PIT_MARK_TINT = "#a3a3a3";

export default function SocPanel({ profile }: { profile: EnergyProfile }) {
  const pitLaps = profile.laps.filter((lap) => lap.pit !== 0).map((lap) => lap.lap);

  return (
    <figure
      data-testid="energy-soc"
      className="rounded border border-neutral-800 bg-neutral-900/40 p-3"
    >
      <figcaption className="text-xs text-neutral-300">
        state of charge — {profile.usable_soc_mj} MJ usable store, the ledger never leaves [0,{" "}
        {profile.usable_soc_mj}] (E-01)
      </figcaption>
      <div className="h-44">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={profile.laps} margin={{ top: 8, right: 12, bottom: 0, left: -16 }}>
            <CartesianGrid stroke="#262626" />
            <XAxis dataKey="lap" stroke="#737373" fontSize={11} />
            <YAxis domain={[0, profile.usable_soc_mj]} stroke="#737373" fontSize={11} />
            <Tooltip
              contentStyle={{ background: "#171717", border: "1px solid #404040", fontSize: 12 }}
              formatter={(value: number) => [`${value.toFixed(2)} MJ`, "SOC"]}
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
      <p className="mt-1 text-xs text-neutral-500">
        {pitLaps.length > 0
          ? `pit stops: ${pitLaps.map((lap) => `lap ${lap}`).join(", ")}`
          : "pit stops: none this run"}
      </p>
    </figure>
  );
}
