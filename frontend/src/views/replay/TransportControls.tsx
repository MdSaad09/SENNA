// Play/pause, the 5.9.3 speed set and a scrub slider. The slider tracks the
// playhead through a transient store subscription writing the DOM directly —
// nothing here re-renders at frame rate.

import { useEffect, useRef } from "react";

import { PLAYBACK_SPEEDS } from "../../config/constants";
import { useReplayStore } from "../../stores/replayStore";

export default function TransportControls({ maxLap }: { maxLap: number }) {
  const playing = useReplayStore((state) => state.playing);
  const speed = useReplayStore((state) => state.speed);
  const setPlaying = useReplayStore((state) => state.setPlaying);
  const setSpeed = useReplayStore((state) => state.setSpeed);
  const scrubTo = useReplayStore((state) => state.scrubTo);

  const slider = useRef<HTMLInputElement | null>(null);
  const lapReadout = useRef<HTMLSpanElement | null>(null);

  useEffect(
    () =>
      useReplayStore.subscribe(
        (state) => state.playheadLap,
        (playheadLap) => {
          if (slider.current !== null) slider.current.value = String(playheadLap);
          if (lapReadout.current !== null) {
            lapReadout.current.textContent = `lap ${Math.max(1, Math.ceil(playheadLap))} / ${maxLap}`;
          }
        },
      ),
    [maxLap],
  );

  return (
    <div className="border-t border-neutral-800 px-4 py-2">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => setPlaying(!playing)}
          className="rounded border border-neutral-700 px-3 py-1 text-sm hover:bg-neutral-800"
        >
          {playing ? "pause" : "play"}
        </button>
        {PLAYBACK_SPEEDS.map((option) => (
          <button
            key={option}
            type="button"
            onClick={() => setSpeed(option)}
            className={`rounded px-2 py-1 text-xs ${
              option === speed
                ? "bg-neutral-700 text-neutral-100"
                : "text-neutral-400 hover:bg-neutral-800"
            }`}
          >
            {option}x
          </button>
        ))}
        <span ref={lapReadout} className="ml-2 font-mono text-xs text-neutral-400">
          lap 1 / {maxLap}
        </span>
        <input
          ref={slider}
          type="range"
          min={0}
          max={maxLap}
          step={0.01}
          defaultValue={0}
          onChange={(event) => scrubTo(Number(event.target.value), maxLap)}
          aria-label="scrub laps"
          className="ml-auto w-64 accent-neutral-400"
        />
      </div>
      <p className="mt-1 text-xs text-neutral-600">
        mid-lap positions are illustrative — the simulator is lap-quantised, motion
        between laps is spline-interpolated from gap-to-leader (stylised); in-pit cars
        pull aside, there is no modelled pit lane
      </p>
    </div>
  );
}
