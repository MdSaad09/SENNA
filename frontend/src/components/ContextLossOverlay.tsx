// E-18: browsers reclaim WebGL contexts under memory pressure, and a black canvas
// with no explanation reads as a crash. preventDefault on the lost event is the
// WebGL contract for allowing restoration; the overlay carries the reload path.

import { useEffect } from "react";

import { useUiStore } from "../stores/uiStore";

export function useContextLoss(canvas: HTMLCanvasElement | null): void {
  const setContextLost = useUiStore((state) => state.setContextLost);

  useEffect(() => {
    if (canvas === null) return;
    const onLost = (event: Event) => {
      event.preventDefault();
      setContextLost(true);
    };
    const onRestored = () => setContextLost(false);

    canvas.addEventListener("webglcontextlost", onLost);
    canvas.addEventListener("webglcontextrestored", onRestored);
    return () => {
      canvas.removeEventListener("webglcontextlost", onLost);
      canvas.removeEventListener("webglcontextrestored", onRestored);
    };
  }, [canvas, setContextLost]);
}

export function ContextLossOverlay() {
  const contextLost = useUiStore((state) => state.contextLost);
  if (!contextLost) return null;

  return (
    <div
      role="alert"
      className="absolute inset-0 z-20 grid place-items-center bg-senna-ground/90"
    >
      <div className="text-center">
        <p className="text-sm text-senna-muted">
          The browser reclaimed the 3D context — usually memory pressure, not a crash.
        </p>
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="mt-4 rounded border border-senna-line px-4 py-1.5 text-sm hover:bg-senna-raised"
        >
          Reload the view
        </button>
      </div>
    </div>
  );
}
