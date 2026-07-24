// Reads the renderer's own accounting between frames — with autoReset on, gl.info
// holds the last completed frame's totals — and publishes to the perf bus. The
// 5.10.3 draw-call budget is asserted here, where it is actually measurable.

import { useFrame, useThree } from "@react-three/fiber";
import { useEffect, useRef } from "react";

import { MAX_DRAW_CALLS_REPLAY, PERF_SAMPLE_MS } from "../config/constants";
import { publishPerf, type PerfSnapshot } from "./perfBus";

const FPS_WINDOW = 60; // operational — one second of samples at the 60 fps target

export default function PerfProbe() {
  const { gl } = useThree();
  const deltas = useRef<number[]>([]);
  const warned = useRef(false);

  // with bloom on, the composer renders several passes per frame and autoReset
  // would zero the counters at each one — reset once per frame here instead, so
  // the interval below always reads a full frame's total
  useEffect(() => {
    gl.info.autoReset = false;
    return () => {
      gl.info.autoReset = true;
    };
  }, [gl]);

  useFrame((_, delta) => {
    gl.info.reset();
    deltas.current.push(delta);
    if (deltas.current.length > FPS_WINDOW) deltas.current.shift();
  });

  useEffect(() => {
    const interval = setInterval(() => {
      const elapsed = deltas.current.reduce((sum, d) => sum + d, 0);
      const sample: PerfSnapshot = {
        calls: gl.info.render.calls,
        triangles: gl.info.render.triangles,
        fps: elapsed > 0 ? deltas.current.length / elapsed : 0,
      };
      publishPerf(sample);
      // the Chrome-trace session reads this while the dev overlay is closed
      (globalThis as Record<string, unknown>).__SENNA_PERF = sample;

      if (sample.calls > MAX_DRAW_CALLS_REPLAY && !warned.current) {
        warned.current = true;
        console.warn(
          `draw calls ${sample.calls} exceed the 5.10.3 budget of ${MAX_DRAW_CALLS_REPLAY}`,
        );
      }
    }, PERF_SAMPLE_MS);
    return () => {
      clearInterval(interval);
      // the canvas is gone (e.g. navigating to the 2D energy route) — zero the bus so
      // the dev overlay never shows the last route's draw calls as if they were live
      const cleared: PerfSnapshot = { calls: 0, triangles: 0, fps: 0 };
      publishPerf(cleared);
      (globalThis as Record<string, unknown>).__SENNA_PERF = cleared;
    };
  }, [gl]);

  return null;
}
