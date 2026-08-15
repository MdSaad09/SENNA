// Every compound's fitted decay on one pair of axes.
//
// The 3D surface 5.10.2 asks for shows one compound at a time, and it renders nearly flat
// — which is the finding, not a bug: at most circuits the fitted decay costs a few percent
// of grip across a stint, and what actually ends the stint is the failure cliff. A surface
// cannot show that, because the cliff is a discrete event rather than a slope.
//
// This chart can. grip(age) = 1 - a*age^b per compound, each drawn to its own cliff, with
// the cliff as a dashed line. Read together: the soft loses more grip per lap AND fails
// earlier, which is the whole trade the agent is deciding about when it pits.

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

import type { DegradationCurve } from "../../api/types";
import { CHART, COMPOUND_COLOURS } from "../../config/palette";

/** The fitted law, senna/physics deg model: grip falls as a power of tyre age. */
function grip(curve: DegradationCurve, age: number): number {
  return 1 - curve.a * Math.pow(age, curve.b);
}

export default function GripCurves({ curves }: { curves: DegradationCurve[] }) {
  if (curves.length === 0) return null;

  const lastAge = Math.max(...curves.map((curve) => curve.cliff_age));
  const rows = Array.from({ length: lastAge + 1 }, (_, age) => {
    const row: Record<string, number> = { age };
    for (const curve of curves) {
      // stop each line at its own cliff: beyond it the tyre has failed, and a fitted
      // curve extrapolated past the failure it caused is a line about nothing
      if (age <= curve.cliff_age) row[curve.compound] = grip(curve, age);
    }
    return row;
  });

  return (
    <div data-testid="grip-curves" className="h-52 w-full">
      <ResponsiveContainer>
        <LineChart data={rows} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
          <CartesianGrid stroke={CHART.gridLine} />
          <XAxis dataKey="age" stroke={CHART.axis} fontSize={11} />
          <YAxis
            stroke={CHART.axis}
            fontSize={11}
            width={40}
            domain={["auto", 1]}
            tickFormatter={(value: number) => value.toFixed(2)}
          />
          {curves.map((curve) => (
            <ReferenceLine
              key={`cliff-${curve.compound}`}
              x={curve.cliff_age}
              stroke={COMPOUND_COLOURS[curve.compound] ?? CHART.axis}
              strokeDasharray="2 3"
              strokeOpacity={0.8}
            />
          ))}
          {curves.map((curve) => (
            <Line
              key={curve.compound}
              type="monotone"
              dataKey={curve.compound}
              stroke={COMPOUND_COLOURS[curve.compound] ?? CHART.axis}
              strokeWidth={2}
              strokeDasharray={curve.low_confidence ? "4 3" : undefined}
              dot={false}
              connectNulls={false}
              isAnimationActive={false}
            />
          ))}
          <Tooltip
            contentStyle={{
              background: CHART.tooltipBg,
              border: `1px solid ${CHART.tooltipLine}`,
              fontSize: 12,
            }}
            labelFormatter={(age) => `age ${age} laps`}
            formatter={(value: number, name) => [value.toFixed(3), String(name)]}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
