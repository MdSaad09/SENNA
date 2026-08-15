// The lap unrolled into a straight line, so the shape of a circuit is readable without
// orbiting a 3D model: where the full-throttle stretches are, where the braking zones
// fall, and how much of the lap each takes up.
//
// Both come from the F04 pipeline and both are inferred rather than official — X-mode
// sections from the longest full-throttle runs, braking zones from telemetry speed drops
// above 50 km/h. The legend on the canvas says so and so does the note under this strip.

import type { BrakingZone, XModeSection } from "../../api/types";
import { SCENE } from "../../config/palette";

interface LapStripProps {
  lapLengthM: number;
  xmode: XModeSection[];
  braking: BrakingZone[];
}

export default function LapStrip({ lapLengthM, xmode, braking }: LapStripProps) {
  const pct = (metres: number) => `${(metres / lapLengthM) * 100}%`;

  return (
    <div data-testid="lap-strip">
      <div className="relative h-6 w-full overflow-hidden rounded-panel bg-senna-raised">
        {xmode.map((section) => (
          <span
            key={`x-${section.start_m}`}
            title={`x-mode ${Math.round(section.length_m)} m`}
            className="absolute inset-y-0"
            style={{
              left: pct(section.start_m),
              width: pct(section.length_m),
              backgroundColor: SCENE.xmode,
              opacity: 0.75,
            }}
          />
        ))}
        {braking.map((zone) => (
          <span
            key={`b-${zone.start_m}`}
            title={`braking ${Math.round(zone.entry_kmh)} to ${Math.round(zone.min_kmh)} km/h`}
            className="absolute inset-y-0"
            style={{
              left: pct(zone.start_m),
              width: pct(Math.max(zone.end_m - zone.start_m, lapLengthM * 0.004)),
              backgroundColor: SCENE.braking,
            }}
          />
        ))}
      </div>
      <div className="mt-1 flex justify-between text-micro text-senna-ghost">
        <span>start / finish</span>
        <span>{(lapLengthM / 1000).toFixed(3)} km</span>
      </div>
    </div>
  );
}
