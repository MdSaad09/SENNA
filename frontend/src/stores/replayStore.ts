// Playback state for the replay view. The clock math is a pure function so the
// store, the useFrame loop and the tests all share one definition; the store is
// read with getState() inside the frame loop and written transiently, so nothing
// re-renders at 60 fps.

import { create } from "zustand";
import { subscribeWithSelector } from "zustand/middleware";

import { PLAYBACK_SPEEDS } from "../config/constants";

export function advancePlayhead(
  playheadLap: number,
  deltaS: number,
  speed: number,
  nominalLapS: number,
  maxLap: number,
): { playheadLap: number; playing: boolean } {
  const next = playheadLap + (deltaS * speed) / nominalLapS;
  if (next >= maxLap) return { playheadLap: maxLap, playing: false };
  return { playheadLap: Math.max(0, next), playing: true };
}

interface ReplayState {
  playing: boolean;
  speed: number;
  playheadLap: number;
  selectedCarId: number | null;
  setPlaying(playing: boolean): void;
  setSpeed(speed: number): void;
  tick(deltaS: number, nominalLapS: number, maxLap: number): void;
  scrubTo(lap: number, maxLap: number): void;
  selectCar(id: number | null): void;
  reset(): void;
}

export const useReplayStore = create<ReplayState>()(
  subscribeWithSelector((set, get) => ({
    playing: false,
    speed: PLAYBACK_SPEEDS[0],
    playheadLap: 0,
    selectedCarId: null,
    setPlaying: (playing) => set({ playing }),
    setSpeed: (speed) => set({ speed }),
    tick: (deltaS, nominalLapS, maxLap) => {
      const { playheadLap, speed, playing } = get();
      if (!playing) return;
      set(advancePlayhead(playheadLap, deltaS, speed, nominalLapS, maxLap));
    },
    scrubTo: (lap, maxLap) => set({ playheadLap: Math.min(Math.max(lap, 0), maxLap) }),
    selectCar: (id) => set({ selectedCarId: id }),
    reset: () => set({ playing: false, playheadLap: 0, selectedCarId: null }),
  })),
);
