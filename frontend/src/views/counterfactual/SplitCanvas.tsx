// The split viewport that keeps F-28 honest: ONE canvas, absolutely positioned
// behind the two pane divs, with each pane a drei View that scissor-renders its own
// scene into its own rectangle of the shared GL context. Both panes inherit the one
// root camera, and the single OrbitControls listens on the wrapper element — so
// dragging anywhere orbits both panes in lockstep, and any visual difference
// between the halves is strategy, never viewpoint (F-24).
//
// Bloom is deliberately absent: it composits the root scene through an effect pass
// that would fight the scissored View renders, so the quality toggle has no effect
// on this route and the transport caption says so.

import { OrbitControls, View } from "@react-three/drei";
import { Canvas } from "@react-three/fiber";
import { Suspense, useState, type MutableRefObject, type RefObject } from "react";

import type { CircuitDetail, LapFrame } from "../../api/types";
import { ContextLossOverlay, useContextLoss } from "../../components/ContextLossOverlay";
import PerfProbe from "../../components/PerfProbe";
import SceneFrame from "../../components/SceneFrame";
import { CAMERA, DPR_RANGE, PANE_BACKGROUND } from "../../config/constants";
import type { PlaybackStore } from "../replay/ReplayScene";
import ReplayScene from "../replay/ReplayScene";

interface ScenePaneProps {
  detail: CircuitDetail;
  gltfUrl: string;
  frames: LapFrame[];
  nominalLapS: number;
  store: PlaybackStore;
  egoBadge: string | null;
}

// one pane's scene, tunnelled into the shared canvas. The explicit background is
// load-bearing: drei's scissored path disables autoClear and never clears a View
// whose scene has none, so cars would smear trails without it.
export function ScenePane({
  detail,
  gltfUrl,
  frames,
  nominalLapS,
  store,
  egoBadge,
}: ScenePaneProps) {
  return (
    <View className="h-full w-full">
      <color attach="background" args={[PANE_BACKGROUND]} />
      <SceneFrame>
        <Suspense fallback={null}>
          <ReplayScene
            detail={detail}
            gltfUrl={gltfUrl}
            frames={frames}
            nominalLapS={nominalLapS}
            store={store}
            driveClock={false}
            labelPolicy="ego"
            egoBadge={egoBadge}
          />
        </Suspense>
      </SceneFrame>
    </View>
  );
}

export default function SplitCanvas({
  eventSource,
}: {
  eventSource: RefObject<HTMLElement>;
}) {
  const [canvasEl, setCanvasEl] = useState<HTMLCanvasElement | null>(null);
  useContextLoss(canvasEl);

  return (
    <div className="absolute inset-0">
      <Canvas
        dpr={DPR_RANGE}
        camera={{
          fov: CAMERA.fov,
          near: CAMERA.near,
          far: CAMERA.far,
          position: [...CAMERA.position],
        }}
        // the wrapper is assigned in the same commit; r3f connects its events in an
        // effect, after which current is never null
        eventSource={eventSource as MutableRefObject<HTMLElement>}
        onCreated={({ gl }) => setCanvasEl(gl.domElement)}
      >
        <View.Port />
        <PerfProbe />
        <OrbitControls makeDefault />
      </Canvas>
      <ContextLossOverlay />
    </div>
  );
}
