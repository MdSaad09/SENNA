import { act, cleanup, render, screen, within } from "@testing-library/react";
import { StrictMode, useState } from "react";
import { afterEach, beforeEach, expect, test } from "vitest";

import { useUiStore } from "../stores/uiStore";
import { ContextLossOverlay, useContextLoss } from "./ContextLossOverlay";

// stands in for CanvasHost: a real DOM canvas wired to the hook, overlay alongside
function LossHarness() {
  // a state ref, so the hook re-wires once the canvas element actually exists
  const [canvas, setCanvas] = useState<HTMLCanvasElement | null>(null);
  useContextLoss(canvas);
  return (
    <>
      <canvas data-testid="gl-canvas" ref={setCanvas} />
      <ContextLossOverlay />
    </>
  );
}

beforeEach(() => {
  act(() => {
    useUiStore.getState().setContextLost(false);
  });
});

afterEach(cleanup);

function loseContext(canvas: HTMLElement): Event {
  const lost = new Event("webglcontextlost", { cancelable: true });
  act(() => {
    canvas.dispatchEvent(lost);
  });
  return lost;
}

test("a lost context is claimed for restoration and the overlay appears (E-18)", () => {
  render(<LossHarness />);
  const lost = loseContext(screen.getByTestId("gl-canvas"));

  // preventDefault is the WebGL contract: without it the browser never fires
  // webglcontextrestored
  expect(lost.defaultPrevented).toBe(true);

  const overlay = screen.getByRole("alert");
  expect(within(overlay).getByRole("button", { name: /reload/i })).toBeInTheDocument();
  expect(useUiStore.getState().contextLost).toBe(true);
});

test("a restored context clears the overlay", () => {
  render(<LossHarness />);
  const canvas = screen.getByTestId("gl-canvas");
  loseContext(canvas);

  act(() => {
    canvas.dispatchEvent(new Event("webglcontextrestored"));
  });
  expect(screen.queryByRole("alert")).toBeNull();
  expect(useUiStore.getState().contextLost).toBe(false);
});

test("StrictMode's double mount still yields exactly one overlay", () => {
  render(
    <StrictMode>
      <LossHarness />
    </StrictMode>,
  );
  loseContext(screen.getByTestId("gl-canvas"));
  expect(screen.getAllByRole("alert")).toHaveLength(1);
});

test("unmounting detaches the listeners: a late loss touches nothing", () => {
  const view = render(<LossHarness />);
  const canvas = screen.getByTestId("gl-canvas");
  view.unmount();

  canvas.dispatchEvent(new Event("webglcontextlost", { cancelable: true }));
  expect(useUiStore.getState().contextLost).toBe(false);
});
