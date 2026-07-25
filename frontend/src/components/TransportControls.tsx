// Play/pause, the 5.9.3 speed set and a scrub slider — presentational since F13,
// because View 2 drives the local replay clock while View 5 relays the same gestures
// to the server as client:* messages. The slider tracks the playhead through the
// injected transient subscription writing the DOM directly — nothing here re-renders
// at frame rate.

import { useEffect, useRef, type ReactNode } from "react";

import { PLAYBACK_SPEEDS } from "../config/constants";

interface TransportControlsProps {
  playing: boolean;
  speed: number;
  maxLap: number;
  onPlayPause(next: boolean): void;
  onSpeed(speed: number): void;
  onScrub(lap: number): void;
  subscribePlayhead(listener: (playheadLap: number) => void): () => void;
  caption: string;
  children?: ReactNode;
}

export default function TransportControls({
  playing,
  speed,
  maxLap,
  onPlayPause,
  onSpeed,
  onScrub,
  subscribePlayhead,
  caption,
  children,
}: TransportControlsProps) {
  const slider = useRef<HTMLInputElement | null>(null);
  const lapReadout = useRef<HTMLSpanElement | null>(null);

  useEffect(() => {
    let shownLap = 0;
    return subscribePlayhead((playheadLap) => {
      if (slider.current !== null) slider.current.value = String(playheadLap);
      const lap = Math.max(1, Math.ceil(playheadLap));
      if (lap !== shownLap && lapReadout.current !== null) {
        shownLap = lap;
        lapReadout.current.textContent = `lap ${lap} / ${maxLap}`;
      }
    });
  }, [maxLap, subscribePlayhead]);

  return (
    <div className="border-t border-neutral-800 px-4 py-2">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => onPlayPause(!playing)}
          className="rounded border border-neutral-700 px-3 py-1 text-sm hover:bg-neutral-800"
        >
          {playing ? "pause" : "play"}
        </button>
        {PLAYBACK_SPEEDS.map((option) => (
          <button
            key={option}
            type="button"
            onClick={() => onSpeed(option)}
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
        {children}
        <input
          ref={slider}
          type="range"
          min={0}
          max={maxLap}
          step={0.01} // operational — a hundredth of a lap: smooth scrub, exact ends
          defaultValue={0}
          onChange={(event) => onScrub(Number(event.target.value))}
          aria-label="scrub laps"
          className="ml-auto w-64 accent-neutral-400"
        />
      </div>
      <p className="mt-1 text-xs text-neutral-600">{caption}</p>
    </div>
  );
}

// the View 2 honesty caption, exported so both replay-shaped views state it verbatim
export const ILLUSTRATIVE_MOTION_CAPTION =
  "mid-lap positions are illustrative — the simulator is lap-quantised, motion " +
  "between laps is spline-interpolated from gap-to-leader (stylised); the pit " +
  "pull-aside is stylised too, there is no modelled pit lane";
