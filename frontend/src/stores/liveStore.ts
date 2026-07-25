// Playback state for the live view. The buffer holds every stored frame the socket
// delivered — the E-16 single source of truth on the client side — so a back-scrub
// replays exactly what arrived, never a refetch. While following, the playhead rides
// the newest lap at the stream's own cadence; scrubbed back, tick advances the local
// clock until it touches the head again and rejoins live.

import { create } from "zustand";
import { subscribeWithSelector } from "zustand/middleware";

import type { DecisionCard, LapFrame } from "../api/types";
import { PLAYBACK_SPEEDS } from "../config/constants";
import { advancePlayhead } from "./replayStore";

// sorted insert that drops duplicates by returning the same array reference — the
// reconnect seek races the stream, so one duplicate frame per reconnect is guaranteed
export function insertFrame(frames: LapFrame[], frame: LapFrame): LapFrame[] {
  const at = frames.findIndex((held) => held.lap >= frame.lap);
  if (at === -1) return [...frames, frame];
  if (frames[at].lap === frame.lap) return frames;
  return [...frames.slice(0, at), frame, ...frames.slice(at)];
}

interface LiveState {
  frames: LapFrame[];
  cards: Map<number, DecisionCard | null>;
  playheadLap: number;
  playing: boolean;
  following: boolean;
  complete: boolean;
  failed: boolean;
  speed: number;
  selectedCarId: number | null;
  receiveLap(frame: LapFrame, card: DecisionCard | null): void;
  tick(deltaS: number, nominalLapS: number, maxLap?: number): void;
  scrubTo(lap: number): void;
  setPlaying(playing: boolean): void;
  setSpeed(speed: number): void;
  selectCar(id: number | null): void;
  markComplete(): void;
  markFailed(): void;
  reset(): void;
}

const idle = () => ({
  frames: [] as LapFrame[],
  cards: new Map<number, DecisionCard | null>(),
  playheadLap: 0,
  playing: true, // the live stream plays as it arrives; pausing is the deliberate act
  following: true,
  complete: false,
  failed: false,
  speed: PLAYBACK_SPEEDS[0],
  selectedCarId: null,
});

export const useLiveStore = create<LiveState>()(
  subscribeWithSelector((set, get) => ({
    ...idle(),
    receiveLap: (frame, card) => {
      const state = get();
      const frames = insertFrame(state.frames, frame);
      const cards = new Map(state.cards).set(frame.lap, card);
      const head = frames[frames.length - 1].lap;
      set({
        frames,
        cards,
        // the stream is the clock while following (E-16: frames arrive on the
        // server's playback cadence); scrubbed back, the buffer just fills
        ...(state.following && state.playing ? { playheadLap: head } : {}),
      });
    },
    tick: (deltaS, nominalLapS) => {
      const { playing, frames, playheadLap, speed, complete, following } = get();
      if (!playing || frames.length === 0) return;
      const head = frames[frames.length - 1].lap;
      const advanced = advancePlayhead(playheadLap, deltaS, speed, nominalLapS, head);
      if (complete) {
        // the buffer holds the whole race: the clamp is the chequered flag
        set(advanced);
        return;
      }
      set({
        playheadLap: advanced.playheadLap,
        // touching the head mid-stream is a buffer underrun, not the end: keep
        // playing and rejoin the live cadence
        following: following || advanced.playheadLap >= head,
      });
    },
    scrubTo: (lap) => {
      const { frames } = get();
      const head = frames.length === 0 ? 0 : frames[frames.length - 1].lap;
      const clamped = Math.min(Math.max(lap, 0), head);
      set({ playheadLap: clamped, following: clamped >= head });
    },
    setPlaying: (playing) => set({ playing }),
    setSpeed: (speed) => set({ speed }),
    selectCar: (id) => set({ selectedCarId: id }),
    markComplete: () => set({ complete: true }),
    markFailed: () => set({ failed: true }),
    reset: () => set(idle()),
  })),
);
