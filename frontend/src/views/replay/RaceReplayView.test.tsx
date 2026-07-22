import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { PLAYBACK_SPEEDS } from "../../config/constants";
import { installFetchStub, lapFrames20 } from "../../test/apiFixtures";
import RaceReplayView from "./RaceReplayView";

vi.mock("@react-three/fiber", async () => (await import("../../test/mockR3F")).fiberMock());
vi.mock("@react-three/drei", async () => (await import("../../test/mockR3F")).dreiMock());

let restoreFetch: () => void;

beforeEach(() => {
  // ?run= is plain view state read from the URL, not router state (plan: deep
  // links are F13's) — jsdom lets the test set it without a router
  window.history.replaceState(null, "", "/replay?run=7");
  restoreFetch = installFetchStub();
});

afterEach(() => {
  cleanup();
  restoreFetch();
  window.history.replaceState(null, "", "/");
});

function renderView() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <RaceReplayView />
    </QueryClientProvider>,
  );
}

test("the transport offers exactly the 5.9.3 playback speeds", async () => {
  renderView();
  for (const speed of PLAYBACK_SPEEDS) {
    expect(await screen.findByRole("button", { name: `${speed}x` })).toBeInTheDocument();
  }
});

test("mid-lap positions carry the illustrative caption (5.10.2 row 2)", async () => {
  renderView();
  // s_track is a display-only synthesis; the caption is the honesty label
  expect((await screen.findAllByText(/illustrative/i)).length).toBeGreaterThan(0);
});

test("the HUD counts the cars in the frame, never a hardcoded 22", async () => {
  renderView();
  expect((await screen.findAllByText(/22 cars/)).length).toBeGreaterThan(0);
});

test("an era-2024 run shows twenty cars", async () => {
  restoreFetch();
  restoreFetch = installFetchStub({ "/frames": lapFrames20 });
  renderView();
  expect((await screen.findAllByText(/20 cars/)).length).toBeGreaterThan(0);
});
