// The 5.9.3 WebSocket client. The server owns the playback clock and replays stored
// frames (E-16), so this class only ferries messages into the live store, resyncs
// after a drop, and retries with a capped backoff. Two protocol facts are load-
// bearing and pinned by tests: resume-from-pause is a seek — only api/ws.py:125's
// seek branch clears the server's paused flag, client:speed does not — and a
// reconnect seek races the frame already in flight, so one duplicate arrives and
// the store's insertFrame drops it.

import {
  WS_RECONNECT_BASE_MS,
  WS_RECONNECT_FACTOR,
  WS_RECONNECT_MAX_MS,
  WS_STATUS_OPEN,
} from "../config/constants";
import { useLiveStore } from "../stores/liveStore";
import type { DecisionCard, LapFrame } from "./types";
import { recordProvenance } from "./provenance";

// operational — mirrors docker-compose / spec 5.11.2 dev value; prod builds bake
// wss:// (F-27, never a Docker hostname). Same ?? shape as client.ts's VITE_API_BASE.
const wsBase: string = import.meta.env.VITE_WS_BASE ?? "ws://localhost:8000/ws";

export function nextBackoffMs(attempt: number): number {
  return Math.min(WS_RECONNECT_BASE_MS * WS_RECONNECT_FACTOR ** attempt, WS_RECONNECT_MAX_MS);
}

interface ServerMessage {
  type: string;
  frame?: LapFrame;
  card?: DecisionCard | null;
  summary?: Record<string, unknown>;
}

const TERMINAL_CLOSES = new Set([4404, 4500]); // no run / broken summary — retrying cannot help

export class LiveSocket {
  private readonly runId: number;
  private readonly path: string;
  private ws: WebSocket | null = null;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private attempt = 0;
  private disposed = false;

  constructor(runId: number) {
    this.runId = runId;
    this.path = `/ws/simulations/${runId}`;
    this.connect();
  }

  private connect(): void {
    const ws = new WebSocket(`${wsBase}/simulations/${this.runId}`);
    this.ws = ws;
    ws.addEventListener("open", () => this.handleOpen());
    ws.addEventListener("message", (event) => this.handleMessage(event as MessageEvent));
    ws.addEventListener("close", (event) => this.handleClose(event as CloseEvent));
  }

  private handleOpen(): void {
    this.attempt = 0;
    recordProvenance({
      method: "WS",
      path: this.path,
      status: WS_STATUS_OPEN,
      xModelVersion: null,
      runId: this.runId,
    });
    const { frames, speed, playing } = useLiveStore.getState();
    const head = frames.length === 0 ? 0 : frames[frames.length - 1].lap;
    if (head === 0) return; // a fresh session: the server's defaults are ours too
    // resync in one path: jump past the buffer, restore the tempo, re-pause if the
    // viewer had paused (the replayed connection always starts unpaused at 1x)
    this.send({ type: "client:seek", lap: head + 1 });
    this.send({ type: "client:speed", speed });
    if (!playing) this.send({ type: "client:pause" });
  }

  private handleMessage(event: MessageEvent): void {
    let message: ServerMessage;
    try {
      message = JSON.parse(String(event.data)) as ServerMessage;
    } catch {
      return; // not ours to crash on — the server never sends non-JSON
    }
    const store = useLiveStore.getState();
    if (message.type === "sim:lap" && message.frame !== undefined) {
      store.receiveLap(message.frame, message.card ?? null);
    } else if (message.type === "sim:complete") {
      store.markComplete();
      recordProvenance({
        method: "WS",
        path: this.path,
        status: 200,
        xModelVersion: null,
        runId: this.runId,
      });
    } else if (message.type === "sim:failed") {
      store.markFailed();
      recordProvenance({
        method: "WS",
        path: this.path,
        status: 500,
        xModelVersion: null,
        runId: this.runId,
      });
    }
    // sim:event is deliberately dropped: the same RaceEvent dicts ride inside every
    // frame, and a second copy would double-count and de-sync from scrubbing
  }

  private handleClose(event: CloseEvent): void {
    if (this.disposed) return;
    recordProvenance({
      method: "WS",
      path: this.path,
      status: event.code,
      xModelVersion: null,
      runId: this.runId,
    });
    const { complete, failed } = useLiveStore.getState();
    if (TERMINAL_CLOSES.has(event.code) || complete || failed) return;
    this.retryTimer = setTimeout(() => {
      this.retryTimer = null;
      this.connect();
    }, nextBackoffMs(this.attempt++));
  }

  sendSpeed(speed: number): void {
    this.send({ type: "client:speed", speed });
  }

  sendPause(): void {
    this.send({ type: "client:pause" });
  }

  sendSeek(lap: number): void {
    this.send({ type: "client:seek", lap });
  }

  dispose(): void {
    this.disposed = true;
    if (this.retryTimer !== null) {
      clearTimeout(this.retryTimer);
      this.retryTimer = null;
    }
    this.ws?.close();
    this.ws = null;
  }

  private send(message: Record<string, unknown>): void {
    if (this.ws !== null && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    }
  }
}
