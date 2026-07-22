// The one canvas a view may own (F-28). Scene children live in a Z-up group — the
// F04 GLB keeps elevation on its third component, so one fixed rotation here spares
// every consumer an axis remap. Context loss wires to the overlay (E-18) and the
// first created context decides the bloom default from its renderer string.

import { Canvas } from "@react-three/fiber";
import { useState, type ReactNode } from "react";
import type { WebGLRenderer } from "three";

import { CAMERA, DPR_RANGE } from "../config/constants";
import { bloomDefault } from "../lib/gpuHeuristic";
import { useUiStore } from "../stores/uiStore";
import Bloom from "./Bloom";
import { ContextLossOverlay, useContextLoss } from "./ContextLossOverlay";
import PerfProbe from "./PerfProbe";

function rendererString(gl: WebGLRenderer): string | null {
  const context = gl.getContext();
  const debugInfo = context.getExtension("WEBGL_debug_renderer_info");
  if (debugInfo === null) return null;
  const unmasked = context.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL);
  return typeof unmasked === "string" ? unmasked : null;
}

export default function CanvasHost({ children }: { children?: ReactNode }) {
  const [canvasEl, setCanvasEl] = useState<HTMLCanvasElement | null>(null);
  const bloomEnabled = useUiStore((state) => state.bloomEnabled);
  const setBloomDefault = useUiStore((state) => state.setBloomDefault);
  useContextLoss(canvasEl);

  return (
    <div className="relative h-full w-full">
      <Canvas
        dpr={DPR_RANGE}
        camera={{
          fov: CAMERA.fov,
          near: CAMERA.near,
          far: CAMERA.far,
          position: [...CAMERA.position],
        }}
        onCreated={({ gl }) => {
          setCanvasEl(gl.domElement);
          const renderer = rendererString(gl);
          setBloomDefault(
            bloomDefault(renderer),
            renderer === null ? "renderer hidden — bloom off" : `heuristic: ${renderer}`,
          );
        }}
      >
        {/* stylised — flat two-light rig: enough ambient to keep shadowed ribbon
            readable, one keylight for car-body shading; nothing physical */}
        <ambientLight intensity={0.7} />
        <directionalLight position={[600, 900, 400]} intensity={1.1} />
        <group rotation={[-Math.PI / 2, 0, 0]}>{children}</group>
        <PerfProbe />
        {bloomEnabled === true && <Bloom />}
      </Canvas>
      <ContextLossOverlay />
    </div>
  );
}
