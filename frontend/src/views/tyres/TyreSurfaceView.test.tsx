import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { clearProvenance, provenanceLog } from "../../api/provenance";
import { installFetchStub } from "../../test/apiFixtures";
import TyreSurfaceView from "./TyreSurfaceView";
import { BrowserRouter } from "react-router-dom";

// The surface mounts a canvas (View 4 is the 3D one), so the R3F boundary is mocked
// exactly as the replay and route tests mock it; the shader never runs under jsdom,
// so the fitted-model assertions read the HTML fit panel and the provenance log.
vi.mock("@react-three/fiber", async () => (await import("../../test/mockR3F")).fiberMock());
vi.mock("@react-three/drei", async () => (await import("../../test/mockR3F")).dreiMock());

let restoreFetch: () => void;

beforeEach(() => {
  window.history.replaceState(null, "", "/tyres");
  clearProvenance();
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
      {/* F23: ?run= and ?circuit= are written through the router now, not with a raw
          history.replaceState the router cannot see */}
      <BrowserRouter>
        <TyreSurfaceView />
      </BrowserRouter>
    </QueryClientProvider>,
  );
}

test("the fit panel shows the served power-law params, and no lap or energy data is fetched (E-09)", async () => {
  renderView();
  // default selection is the first served curve: bahrain 2024 HARD, a = 0.000878
  expect(await screen.findByText(/0\.000878/)).toBeInTheDocument();
  const paths = provenanceLog().map((entry) => entry.path);
  expect(paths.some((path) => path.includes("/v1/tyres/"))).toBe(true);
  expect(paths.some((path) => path.includes("/frames"))).toBe(false);
  expect(paths.some((path) => path.includes("/energy"))).toBe(false);
});

test("a cluster transfer names its donor circuits; a thin fit says so instead (T5)", async () => {
  renderView();
  await screen.findByText(/0\.000878/); // wait for the curves to land

  fireEvent.change(screen.getByLabelText(/era/i), { target: { value: "2026" } });
  fireEvent.change(screen.getByLabelText(/compound/i), { target: { value: "HARD" } });
  const transfer = await screen.findByTestId("fit-confidence");
  expect(within(transfer).getByText(/cluster transfer \(T5\)/i)).toBeInTheDocument();
  expect(within(transfer).getByText(/australian/i)).toBeInTheDocument();
  expect(within(transfer).queryByText(/thin fit/i)).toBeNull();

  fireEvent.change(screen.getByLabelText(/era/i), { target: { value: "2024" } });
  fireEvent.change(screen.getByLabelText(/compound/i), { target: { value: "MEDIUM" } });
  const thin = await screen.findByTestId("fit-confidence");
  expect(within(thin).getByText(/thin fit/i)).toBeInTheDocument();
  expect(within(thin).queryByText(/cluster transfer/i)).toBeNull();
});

test("the temperature axis carries the unmissable not-fitted label (decision 1)", async () => {
  renderView();
  expect(
    await screen.findByText(/temperature response — stylised illustration, not fitted/i),
  ).toBeInTheDocument();
});

test("a circuit with no fitted block gets an honest empty state, not a broken surface", async () => {
  window.history.replaceState(null, "", "/tyres?circuit=french_grand_prix");
  renderView();
  expect(await screen.findByText(/no degradation fits/i)).toBeInTheDocument();
  expect(screen.queryByTestId("fit-confidence")).toBeNull();
});
