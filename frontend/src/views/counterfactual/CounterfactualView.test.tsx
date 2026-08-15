import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { useReplayStore } from "../../stores/replayStore";
import {
  counterfactualAgentFrames,
  counterfactualAgentRun,
  counterfactualBaselineFramesShort,
  counterfactualBaselineRun,
  installFetchStub,
  raceDetail2024,
} from "../../test/apiFixtures";
import CounterfactualView from "./CounterfactualView";
import { BrowserRouter } from "react-router-dom";

vi.mock("@react-three/fiber", async () => (await import("../../test/mockR3F")).fiberMock());
vi.mock("@react-three/drei", async () => (await import("../../test/mockR3F")).dreiMock());

let restoreFetch: () => void;

beforeEach(() => {
  window.history.replaceState(null, "", "/counterfactual?run=41");
  restoreFetch = installFetchStub();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  restoreFetch();
  window.history.replaceState(null, "", "/");
});

function renderView(inStrictMode = false) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = (
    <QueryClientProvider client={queryClient}>
      {/* F23: a router, and a browser one — the view writes ?run= back through it,
          and these tests assert that lands in window.location where a share copies it */}
      <BrowserRouter>
        <CounterfactualView />
      </BrowserRouter>
    </QueryClientProvider>
  );
  render(inStrictMode ? <StrictMode>{view}</StrictMode> : view);
}

function canvasCount(): number {
  return document.querySelectorAll('[data-testid="r3f-canvas"]').length;
}

test("a deep link posts one counterfactual under StrictMode and writes run= back", async () => {
  window.history.replaceState(null, "", "/counterfactual?year=2024&round=1&driver=C07");
  const fetchSpy = vi.spyOn(globalThis, "fetch");
  renderView(true); // explicit StrictMode: the double-mount must not double-POST

  const posts = () =>
    fetchSpy.mock.calls.filter(
      ([input, init]) =>
        init?.method === "POST" && String(input).includes("/v1/counterfactuals"),
    );
  await waitFor(() => expect(posts()).toHaveLength(1));
  await waitFor(() => expect(window.location.search).toContain("run=41"));
  expect(posts()).toHaveLength(1);

  const [, init] = posts()[0];
  expect(JSON.parse(String(init?.body))).toMatchObject({
    year: 2024,
    round: 1,
    driver: "C07",
  });
});

test("an existing run= skips the POST entirely", async () => {
  const fetchSpy = vi.spyOn(globalThis, "fetch");
  renderView();
  await screen.findByTestId("counterfactual-honesty");
  const posts = fetchSpy.mock.calls.filter(([, init]) => init?.method === "POST");
  expect(posts).toHaveLength(0);
});

test("mounting resets playback state left over from another view", async () => {
  // arrive from View 2 with the store still running — the pair must start clean
  useReplayStore.setState({ playing: true, playheadLap: 33 });
  renderView();
  await waitFor(() => expect(useReplayStore.getState().playheadLap).toBe(0));
  expect(useReplayStore.getState().playing).toBe(false);
});

test("a still-running baseline keeps exactly one canvas and says so", async () => {
  restoreFetch();
  restoreFetch = installFetchStub({
    "/v1/simulations/42": { ...counterfactualBaselineRun, status: "running", finished_at: null },
  });
  renderView();
  expect((await screen.findAllByText(/running/i)).length).toBeGreaterThan(0);
  expect(canvasCount()).toBe(1);
});

test("a failed baseline is stated honestly with the canvas still up", async () => {
  restoreFetch();
  restoreFetch = installFetchStub({
    "/v1/simulations/42": { ...counterfactualBaselineRun, status: "failed" },
  });
  renderView();
  expect((await screen.findAllByText(/failed/i)).length).toBeGreaterThan(0);
  expect(canvasCount()).toBe(1);
});

test("missing params keep exactly one canvas and no comparison", async () => {
  window.history.replaceState(null, "", "/counterfactual");
  renderView();
  await waitFor(() => expect(canvasCount()).toBe(1));
  expect(screen.queryByText(/strategies diverge/i)).toBeNull();
});

test("the honesty header states the era, the pending clause and the real result (F-24)", async () => {
  renderView();
  const honesty = await screen.findByTestId("counterfactual-honesty");
  expect(honesty).toHaveTextContent("in-simulator comparison under stated assumptions");
  expect(honesty).toHaveTextContent(/2024/); // the era line comes from the run config
  expect(honesty).toHaveTextContent(/pending-F14/); // F14 has not landed its fine-tune
  expect(honesty).toHaveTextContent(raceDetail2024.event_name);
  // the driver's actual result, read from GET /races — C07 finished P14 there
  expect(honesty.textContent).toMatch(/C07[\s\S]*P14/);
});

test("the pending-F14 clause disappears once the era-matched model is real", async () => {
  restoreFetch();
  restoreFetch = installFetchStub({
    // the frames override must come first: "/v1/simulations/41" alone would also
    // swallow the /41/frames request and feed it a run object
    "/v1/simulations/41/frames": counterfactualAgentFrames,
    "/v1/simulations/41": {
      ...counterfactualAgentRun,
      config: { ...counterfactualAgentRun.config, era_matched_model: "stage-c-2024" },
      summary: { ...counterfactualAgentRun.summary, era_matched_model: "stage-c-2024" },
    },
  });
  renderView();
  const honesty = await screen.findByTestId("counterfactual-honesty");
  expect(honesty).toHaveTextContent(/2024/);
  expect(honesty.textContent).not.toContain("pending-F14");
});

test("the divergence caption names the first differing lap", async () => {
  renderView();
  // the pair fixture: the agent stops on lap 3, the real strategy on lap 5
  expect(await screen.findByText(/strategies diverge on lap 3/i)).toBeInTheDocument();
});

test("the delta mirror rows carry baseline minus agent with an explicit sign", async () => {
  renderView();
  const mirror = await screen.findByTestId("delta-mirror");
  const rows = within(mirror).getAllByRole("listitem");
  expect(rows).toHaveLength(6); // the shared lap range of the pair fixture
  expect(rows[0]).toHaveAttribute("data-lap", "1");
  expect(rows[rows.length - 1]).toHaveAttribute("data-lap", "6");
  for (const row of rows) {
    expect(row).toHaveAttribute("data-delta", "2"); // baseline P5 - agent P3
    expect(row).toHaveTextContent("+2"); // the sign is the convention, so it shows
  }
});

test("a shorter baseline is stated: baseline ends on lap 4", async () => {
  restoreFetch();
  restoreFetch = installFetchStub({
    "/v1/simulations/42/frames": counterfactualBaselineFramesShort,
  });
  renderView();
  expect(await screen.findByText(/baseline ends on lap 4/i)).toBeInTheDocument();
  const mirror = await screen.findByTestId("delta-mirror");
  expect(within(mirror).getAllByRole("listitem")).toHaveLength(4); // truncated
});

test("the panes caption their sides and the baseline never claims to be the agent", async () => {
  renderView();
  const agentPane = await screen.findByTestId("pane-agent");
  const baselinePane = await screen.findByTestId("pane-baseline");
  expect(agentPane.textContent).toMatch(/SENNA agent strategy/i);
  expect(baselinePane.textContent).toMatch(/actual 2024 strategy \(replayed in-simulator\)/i);
  // jsdom cannot see into the mocked scene, so the pane's whole text stands in for
  // its ego label: nothing on the baseline side may read "agent"
  expect(baselinePane.textContent).not.toMatch(/agent/i);
  expect(canvasCount()).toBe(1); // F-28: two panes, one canvas
});
