// The one clock of the split view. Both panes read the replay store and neither
// ticks (driveClock={false}), so "synced lap clocks" is true by construction —
// this DOM-side rAF loop is the only writer. It lives outside the canvas because
// the jsdom test harness mocks away useFrame, and a clock the tests cannot crank
// would be a clock the tests cannot pin.

import { useEffect } from "react";

import { useReplayStore } from "../../stores/replayStore";

interface CounterfactualClockProps {
  nominalLapS: number;
  sharedMaxLap: number;
}

export default function CounterfactualClock({
  nominalLapS,
  sharedMaxLap,
}: CounterfactualClockProps) {
  useEffect(() => {
    let handle: number;
    let lastMs: number | null = null;
    const loop = (nowMs: number) => {
      if (lastMs !== null) {
        useReplayStore.getState().tick((nowMs - lastMs) / 1000, nominalLapS, sharedMaxLap);
      }
      lastMs = nowMs;
      handle = requestAnimationFrame(loop);
    };
    handle = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(handle);
  }, [nominalLapS, sharedMaxLap]);

  return null;
}
