import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { DEFAULT_GRID_POSITION } from "../../config/constants";
import {
  decisionCardForLap,
  installFetchStub,
  liveStreamFrames,
  simLapMessages,
} from "../../test/apiFixtures";
import { FakeWebSocket, installFakeWebSocket } from "../../test/fakeSocket";
import LiveSimulationView from "./LiveSimulationView";

vi.mock("@react-three/fiber", async () => (await import("../../test/mockR3F")).fiberMock());
vi.mock("@react-three/drei", async () => (await import("../../test/mockR3F")).dreiMock());

let restoreFetch: () => void;
let restoreSocket: () => void;

beforeEach(() => {
  window.history.replaceState(null, "", "/live?run=7");
  restoreFetch = installFetchStub();
  restoreSocket = installFakeWebSocket();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  restoreFetch();
  restoreSocket();
  window.history.replaceState(null, "", "/");
});

function renderView(inStrictMode = false) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = (
    <QueryClientProvider client={queryClient}>
      <LiveSimulationView />
    </QueryClientProvider>
  );
  render(inStrictMode ? <StrictMode>{view}</StrictMode> : view);
}

async function liveWire(): Promise<FakeWebSocket> {
  return waitFor(() => {
    expect(FakeWebSocket.instances.length).toBeGreaterThan(0);
    return FakeWebSocket.instances[FakeWebSocket.instances.length - 1];
  });
}

async function openStream(laps: number): Promise<FakeWebSocket> {
  const socket = await liveWire();
  const frames = liveStreamFrames(laps);
  act(() => {
    socket.serverOpen();
    for (const message of simLapMessages(frames, decisionCardForLap)) {
      socket.serverMessage(message);
    }
  });
  return socket;
}

test("scrubbing back mid-stream replays the exact stored lap without asking the server (E-16)", async () => {
  renderView();
  const socket = await openStream(10);

  // following the stream, the newest delivered card is on screen
  expect(await screen.findByText(decisionCardForLap(10).decision)).toBeInTheDocument();

  fireEvent.change(await screen.findByRole("slider", { name: /scrub/i }), {
    target: { value: "3" },
  });

  // the rendered card is lap 3's exact payload — not a neighbour, not a refetch
  expect(await screen.findByText(decisionCardForLap(3).decision)).toBeInTheDocument();
  expect(screen.getByText(decisionCardForLap(3).plain_language)).toBeInTheDocument();
  expect(screen.queryByText(decisionCardForLap(4).decision)).toBeNull();
  expect(screen.queryByText(decisionCardForLap(10).decision)).toBeNull();
  // the buffer answered the scrub alone: no seek went over the wire
  expect(socket.sent.map((message) => message.type)).not.toContain("client:seek");
});

test("all-null cards render the honest empty state, never an error (E-15)", async () => {
  renderView();
  const socket = await liveWire();
  const frames = liveStreamFrames(5);
  act(() => {
    socket.serverOpen();
    for (const message of simLapMessages(frames)) socket.serverMessage(message);
  });

  const emptyState = await screen.findByText(/no stored explanations/i);
  expect(emptyState.textContent).toMatch(/test-model/); // the line names the version
  expect(screen.queryByText(/error/i)).toBeNull();
  expect(screen.queryByText(/failed/i)).toBeNull();
});

test("pause and resume speak the 5.9.3 protocol: client:pause, then a seek to head + 1", async () => {
  renderView();
  const socket = await openStream(5);

  fireEvent.click(await screen.findByRole("button", { name: "pause" }));
  expect(socket.sent).toContainEqual({ type: "client:pause" });

  // resume is a seek: only api/ws.py's seek branch clears paused (plan divergence 4)
  fireEvent.click(await screen.findByRole("button", { name: "play" }));
  expect(socket.sent).toContainEqual({ type: "client:seek", lap: 6 });
});

test("a speed button sends client:speed", async () => {
  renderView();
  const socket = await openStream(5);

  fireEvent.click(await screen.findByRole("button", { name: "30x" }));
  expect(socket.sent).toContainEqual({ type: "client:speed", speed: 30 });
});

test("the header states the agent races in the simulator, not live timing (R-05)", async () => {
  renderView();
  expect(await screen.findByText(/not live timing/i)).toBeInTheDocument();
});

test("a cold deep link posts one simulation under StrictMode and writes run= back", async () => {
  window.history.replaceState(null, "", "/live?circuit=bahrain_grand_prix&seed=42");
  const fetchSpy = vi.spyOn(globalThis, "fetch");
  renderView(true); // explicit StrictMode: the double-mount must not double-POST

  const posts = () =>
    fetchSpy.mock.calls.filter(
      ([input, init]) => init?.method === "POST" && String(input).includes("/v1/simulations"),
    );
  await waitFor(() => expect(posts()).toHaveLength(1));
  await waitFor(() => expect(window.location.search).toContain("run=7"));
  expect(posts()).toHaveLength(1);

  const [, init] = posts()[0];
  expect(JSON.parse(String(init?.body))).toMatchObject({
    circuit_id: "bahrain_grand_prix",
    seed: 42,
    grid_position: DEFAULT_GRID_POSITION,
  });
});
