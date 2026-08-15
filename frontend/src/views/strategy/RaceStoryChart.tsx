// The race, as one picture.
//
// Position against lap for all 22 cars: the field in grey, the agent in the accent, P1
// at the top. Stops are marked on the agent's line and safety-car laps are shaded, so
// the two things that decide a strategy — when you stopped and what the race did to you
// — are visible together rather than described in separate panels.
//
// Every point is a served CarState.position. Nothing is modelled here.

import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { LapFrame } from "../../api/types";
import { CHART, PALETTE } from "../../config/palette";
import type { Stint } from "./stints";

interface RaceStoryChartProps {
  frames: LapFrame[];
  egoId: number;
  stints: Stint[];
}

/** One row per lap, one column per car: what recharts wants. */
function positionRows(frames: LapFrame[]): Record<string, number>[] {
  return frames.map((frame) => {
    const row: Record<string, number> = { lap: frame.lap };
    for (const car of frame.cars) row[`c${car.id}`] = car.position;
    return row;
  });
}

/** Laps the field was under safety car or VSC — the race interrupting the strategy. */
function neutralisedLaps(frames: LapFrame[]): number[] {
  return frames
    .filter((frame) => frame.events.some((event) => event.kind === "sc" || event.kind === "vsc"))
    .map((frame) => frame.lap);
}

export default function RaceStoryChart({ frames, egoId, stints }: RaceStoryChartProps) {
  if (frames.length === 0) return null;

  const rows = positionRows(frames);
  const carIds = frames[0].cars.map((car) => car.id);
  const lastLap = frames[frames.length - 1].lap;
  const fieldSize = frames[0].cars.length;
  const neutralised = neutralisedLaps(frames);
  const stopLaps = stints.slice(1).map((stint) => stint.startLap);

  return (
    <div data-testid="race-story" className="h-64 w-full">
      <ResponsiveContainer>
        <LineChart data={rows} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
          <CartesianGrid stroke={CHART.gridLine} />
          <XAxis
            dataKey="lap"
            stroke={CHART.axis}
            fontSize={11}
            ticks={[1, ...stopLaps, lastLap]}
          />
          {/* reversed: P1 belongs at the top, the way a classification reads */}
          <YAxis
            reversed
            domain={[1, fieldSize]}
            ticks={[1, 5, 10, 15, 20]}
            stroke={CHART.axis}
            fontSize={11}
            width={28}
          />

          {neutralised.map((lap) => (
            <ReferenceArea
              key={`sc-${lap}`}
              x1={lap - 0.5}
              x2={lap + 0.5}
              fill={PALETTE.muted}
              fillOpacity={0.07}
              ifOverflow="extendDomain"
            />
          ))}

          {carIds
            .filter((id) => id !== egoId)
            .map((id) => (
              <Line
                key={id}
                type="monotone"
                dataKey={`c${id}`}
                stroke={CHART.axis}
                strokeWidth={1}
                strokeOpacity={0.45}
                dot={false}
                isAnimationActive={false}
              />
            ))}

          {stopLaps.map((lap) => (
            <ReferenceLine
              key={`stop-${lap}`}
              x={lap}
              stroke={PALETTE.accent}
              strokeDasharray="3 3"
              strokeOpacity={0.6}
            />
          ))}

          <Line
            type="monotone"
            dataKey={`c${egoId}`}
            stroke={PALETTE.accent}
            strokeWidth={2.5}
            dot={false}
            isAnimationActive={false}
          />

          <Tooltip
            contentStyle={{
              background: CHART.tooltipBg,
              border: `1px solid ${CHART.tooltipLine}`,
              fontSize: 12,
            }}
            labelFormatter={(lap) => `lap ${lap}`}
            formatter={(value, name) =>
              name === `c${egoId}` ? [`P${value}`, "agent"] : [`P${value}`, String(name)]
            }
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
