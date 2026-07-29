import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { WS_STATUS_OPEN } from "../config/constants";
import { useLiveStore } from "../stores/liveStore";
import { FakeWebSocket, installFakeWebSocket } from "../test/fakeSocket";
import { LiveSocket } from "./liveSocket";
import { clearProvenance, provenanceLog } from "./provenance";

let restoreSocket: () => void;
let sockets: LiveSocket[] = [];

function connect(runId = 7, opts?: { startLap?: number; speed?: number }): LiveSocket {
  const socket = new LiveSocket(runId, opts);
  sockets.push(socket);
  return socket;
}

function wire(index = 0): FakeWebSocket {
  return FakeWebSocket.instances[index];
}

function lapMessage(lap: number) {
  return {
    type: "sim:lap",
    frame: {
      lap,
      cars: [],
      agent: {
        soc_mj: 2.0,
        harvest_mj: 3.0,
        deploy_mj: 2.8,
        mode: 1,
        action: {},
        reward_terms: {},
        mask_reasons: {},
      },
      events: [],
    },
    card: null,
  };
}

beforeEach(() => {
  vi.useFakeTimers();
  restoreSocket = installFakeWebSocket();
  useLiveStore.getState().reset();
  clearProvenance();
  sockets = [];
});

afterEach(() => {
  for (const socket of sockets) socket.dispose();
  restoreSocket();
  vi.useRealTimers();
  vi.unstubAllEnvs();
});

test("the socket url comes from VITE_WS_BASE", async () => {
  vi.stubEnv("VITE_WS_BASE", "ws://example.test/ws");
  vi.resetModules(); // a fresh module instance, whichever moment it reads the env
  const { LiveSocket: FreshLiveSocket } = await import("./liveSocket");
  const socket = new FreshLiveSocket(7);
  expect(wire().url).toBe("ws://example.test/ws/simulations/7");
  socket.dispose();
});

test("without VITE_WS_BASE the dev fallback names localhost:8000", () => {
  connect(7);
  expect(wire().url).toBe("ws://localhost:8000/ws/simulations/7");
});

test("the first connect sends no client:seek", () => {
  connect();
  wire().serverOpen();
  // an empty buffer has nothing to seek past — a seek would only earn a duplicate
  expect(wire().sent.map((message) => message.type)).not.toContain("client:seek");
});

test("a reconnect syncs with client:seek to head + 1, then client:speed", () => {
  connect();
  wire().serverOpen();
  for (let lap = 1; lap <= 3; lap++) wire().serverMessage(lapMessage(lap));
  wire().serverClose(1006); // abnormal closure — the demo network hiccup

  vi.advanceTimersByTime(500);
  const rejoined = wire(1);
  rejoined.serverOpen();
  expect(rejoined.sent[0]).toEqual({ type: "client:seek", lap: 4 });
  expect(rejoined.sent[1]).toEqual({ type: "client:speed", speed: 1 });
});

test("reconnect backoff doubles from 500 ms and caps at 8000 ms", () => {
  connect();

  wire(0).serverClose(1006);
  vi.advanceTimersByTime(499);
  expect(FakeWebSocket.instances).toHaveLength(1);
  vi.advanceTimersByTime(1);
  expect(FakeWebSocket.instances).toHaveLength(2);

  wire(1).serverClose(1006);
  vi.advanceTimersByTime(999);
  expect(FakeWebSocket.instances).toHaveLength(2);
  vi.advanceTimersByTime(1);
  expect(FakeWebSocket.instances).toHaveLength(3);

  wire(2).serverClose(1006);
  vi.advanceTimersByTime(2000);
  expect(FakeWebSocket.instances).toHaveLength(4);

  wire(3).serverClose(1006);
  vi.advanceTimersByTime(4000);
  expect(FakeWebSocket.instances).toHaveLength(5);

  wire(4).serverClose(1006);
  vi.advanceTimersByTime(8000);
  expect(FakeWebSocket.instances).toHaveLength(6);

  // the cap: the next retry still waits 8000, not 16000
  wire(5).serverClose(1006);
  vi.advanceTimersByTime(7999);
  expect(FakeWebSocket.instances).toHaveLength(6);
  vi.advanceTimersByTime(1);
  expect(FakeWebSocket.instances).toHaveLength(7);
});

test("laps replayed across a reconnect land in the buffer once", () => {
  connect();
  wire().serverOpen();
  for (let lap = 1; lap <= 3; lap++) wire().serverMessage(lapMessage(lap));
  wire().serverClose(1006);

  vi.advanceTimersByTime(500);
  const rejoined = wire(1);
  rejoined.serverOpen();
  // E-16: the seek races the stream, so one duplicate frame is guaranteed
  rejoined.serverMessage(lapMessage(3));
  rejoined.serverMessage(lapMessage(4));

  expect(useLiveStore.getState().frames.map((frame) => frame.lap)).toEqual([1, 2, 3, 4]);
});

test("a 4404 close is terminal: no retry timer, no new socket", () => {
  connect();
  wire().serverClose(4404);
  expect(vi.getTimerCount()).toBe(0);
  vi.advanceTimersByTime(60_000);
  expect(FakeWebSocket.instances).toHaveLength(1);
});

test("a 4500 close is terminal: no retry timer, no new socket", () => {
  connect();
  wire().serverClose(4500);
  expect(vi.getTimerCount()).toBe(0);
  vi.advanceTimersByTime(60_000);
  expect(FakeWebSocket.instances).toHaveLength(1);
});

test("the server closing after sim:complete ends the session without a retry", () => {
  connect();
  wire().serverOpen();
  for (let lap = 1; lap <= 2; lap++) wire().serverMessage(lapMessage(lap));
  wire().serverMessage({ type: "sim:complete", summary: { nominal_lap_s: 90 } });
  wire().serverClose(1000);

  expect(useLiveStore.getState().complete).toBe(true);
  expect(vi.getTimerCount()).toBe(0);
  vi.advanceTimersByTime(60_000);
  expect(FakeWebSocket.instances).toHaveLength(1);
});

test("dispose is StrictMode-symmetric: a late close wakes nothing", () => {
  const socket = connect();
  wire().serverOpen();
  socket.dispose();

  wire().serverClose(1006); // the network noticing after the effect cleanup ran
  expect(vi.getTimerCount()).toBe(0);
  vi.advanceTimersByTime(60_000);
  expect(FakeWebSocket.instances).toHaveLength(1);
});

test("a mid-race deep link's first open seeks to the start lap, then sets the speed", () => {
  // E-16: mid-race entry is a seek over stored frames — the empty-buffer early
  // return gives way to the deep link's opts
  connect(7, { startLap: 18, speed: 30 });
  wire().serverOpen();
  expect(wire().sent[0]).toEqual({ type: "client:seek", lap: 18 });
  expect(wire().sent[1]).toEqual({ type: "client:speed", speed: 30 });
});

test("a start lap without a speed seeks and leaves the tempo alone", () => {
  connect(7, { startLap: 18 });
  wire().serverOpen();
  expect(wire().sent).toEqual([{ type: "client:seek", lap: 18 }]);
});

test("start opts speak once: a reconnect resyncs from the buffer, not the deep link", () => {
  connect(7, { startLap: 18, speed: 30 });
  wire().serverOpen();
  for (let lap = 18; lap <= 20; lap++) wire().serverMessage(lapMessage(lap));
  wire().serverClose(1006);

  vi.advanceTimersByTime(500);
  const rejoined = wire(1);
  rejoined.serverOpen();
  // the buffer owns the resync (E-16): head + 1, never the deep-link lap again
  expect(rejoined.sent[0]).toEqual({ type: "client:seek", lap: 21 });
  expect(rejoined.sent).not.toContainEqual({ type: "client:seek", lap: 18 });
});

test("provenance records the socket lifecycle, never a frame", () => {
  connect();
  wire().serverOpen();
  for (let lap = 1; lap <= 30; lap++) wire().serverMessage(lapMessage(lap));
  wire().serverMessage({ type: "sim:complete", summary: { nominal_lap_s: 90 } });
  wire().serverClose(1000);

  // 30 per-frame entries would flush the 50-entry ring and evict the REST entries
  // carrying model_version — exactly open, complete, close, nothing per lap
  const log = provenanceLog();
  expect(log).toHaveLength(3);
  expect(log[0].status).toBe(WS_STATUS_OPEN);
  for (const entry of log) expect(entry.path).toContain("/simulations/7");
});
