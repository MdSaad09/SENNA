import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, render, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { routes } from "./routes";
import { installFetchStub } from "./test/apiFixtures";
import { installFakeWebSocket } from "./test/fakeSocket";

// jsdom has no WebGL: Canvas becomes a bare <canvas> that swallows its children,
// which is exactly the observable F-28 cares about — how many are mounted
vi.mock("@react-three/fiber", async () => (await import("./test/mockR3F")).fiberMock());
vi.mock("@react-three/drei", async () => (await import("./test/mockR3F")).dreiMock());

let restoreFetch: () => void;
let restoreSocket: () => void;

beforeEach(() => {
  restoreFetch = installFetchStub();
  // mounting /live opens a WebSocket; the fake keeps jsdom from throwing on it
  restoreSocket = installFakeWebSocket();
});

afterEach(() => {
  cleanup();
  restoreFetch();
  restoreSocket();
});

function canvasCount(): number {
  return document.querySelectorAll('[data-testid="r3f-canvas"]').length;
}

function renderRouterAt(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  // the QueryClientProvider lives in main.tsx, outside the route table, so the
  // test supplies its own; no retries keeps a broken fetch loudly red
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return router;
}

test("navigation swaps the canvas and never stacks a second one (F-28)", async () => {
  const router = renderRouterAt("/circuit");
  await waitFor(() => expect(canvasCount()).toBe(1));

  // watch the whole document for the forbidden state: two canvases alive at once
  let peak = 1;
  const observer = new MutationObserver(() => {
    peak = Math.max(peak, canvasCount());
  });
  observer.observe(document.body, { childList: true, subtree: true });

  // every canonical section under the three F23 tabs, so the one-canvas rule is
  // proved across the whole map and not just the paths that happen to hold a scene
  const hops: [string, number][] = [
    ["/strategy/setup", 0], // configuration rail and a post-hoc summary, no scene
    ["/strategy/replay?run=7", 1],
    ["/strategy/live?run=7", 1], // F13: CanvasHost mounts unconditionally, picker or stream
    ["/analysis/energy?run=7", 0], // 2D recharts (F11 decision 2), no canvas
    ["/analysis/tyres", 1], // the tyre surface owns a CanvasHost
    ["/analysis/decisions?run=7", 0], // cards are HTML (A-03)
    ["/analysis/counterfactual", 1], // F13: two panes, still one canvas (F-28)
    ["/circuit", 1],
  ];
  for (const [path, expected] of hops) {
    await act(async () => {
      await router.navigate(path);
    });
    await waitFor(() => expect(canvasCount(), `after ${path}`).toBe(expected));
  }

  observer.disconnect();
  expect(peak, "two canvases were mounted at the same time").toBeLessThanOrEqual(1);
});

test("the root path redirects to the strategy setup section", async () => {
  // F23 leads with Strategy; before it, "/" pinned to the circuit explorer
  const router = renderRouterAt("/");
  await waitFor(() => expect(router.state.location.pathname).toBe("/strategy/setup"));
});

test("a legacy path redirects to its section and keeps the query (F15 deep links)", async () => {
  // the demo URLs, the README and scripts/warm_demo.sh all open flat paths carrying
  // a query; losing ?run= in the redirect would land the view unconfigured
  const redirects: [string, string][] = [
    ["/replay?run=7", "/strategy/replay"],
    ["/live?run=7", "/strategy/live"],
    ["/energy?run=7", "/analysis/energy"],
    ["/tyres?run=7", "/analysis/tyres"],
    ["/counterfactual?run=7", "/analysis/counterfactual"],
    ["/circuit?run=7", "/circuit"], // the one path that does not move
  ];
  for (const [legacy, canonical] of redirects) {
    const router = renderRouterAt(legacy);
    await waitFor(() => expect(router.state.location.pathname, legacy).toBe(canonical));
    expect(router.state.location.search, legacy).toBe("?run=7");
    cleanup();
  }
});
