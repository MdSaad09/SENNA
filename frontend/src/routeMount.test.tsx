import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, render, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { routes } from "./routes";
import { installFetchStub } from "./test/apiFixtures";

// jsdom has no WebGL: Canvas becomes a bare <canvas> that swallows its children,
// which is exactly the observable F-28 cares about — how many are mounted
vi.mock("@react-three/fiber", async () => (await import("./test/mockR3F")).fiberMock());
vi.mock("@react-three/drei", async () => (await import("./test/mockR3F")).dreiMock());

let restoreFetch: () => void;

beforeEach(() => {
  restoreFetch = installFetchStub();
});

afterEach(() => {
  cleanup();
  restoreFetch();
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

  const hops: [string, number][] = [
    ["/replay?run=7", 1],
    ["/energy", 0], // the energy view is 2D recharts (decision 2), no canvas
    ["/tyres", 1], // the tyre surface owns a CanvasHost
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

test("the root path redirects to the circuit explorer", async () => {
  const router = renderRouterAt("/");
  await waitFor(() => expect(router.state.location.pathname).toBe("/circuit"));
  await waitFor(() => expect(canvasCount()).toBe(1));
});

test("the live and counterfactual stubs resolve without mounting a canvas", async () => {
  const router = renderRouterAt("/live");
  await waitFor(() => expect(router.state.location.pathname).toBe("/live"));
  expect(canvasCount()).toBe(0);

  await act(async () => {
    await router.navigate("/counterfactual");
  });
  await waitFor(() => expect(router.state.location.pathname).toBe("/counterfactual"));
  expect(canvasCount()).toBe(0);
});
