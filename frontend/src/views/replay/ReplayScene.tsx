// The one useFrame that owns replay playback. Per car: unwrap the per-lap s_track
// fractions into monotone progress, interpolate at the playhead, place the
// instance along the centreline by arc length and point it down the tangent.
// Everything per-frame mutates refs — React re-renders once per lap for the label
// set, never per frame. Mid-lap motion is synthesis, and the caption says so.

import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import { InstancedMesh, Object3D, Quaternion, Vector3 } from "three";

import type { CircuitDetail, LapFrame } from "../../api/types";
import {
  LABEL_HEIGHT_M,
  LOD_DISTANCE_M,
  PIT_LATERAL_OFFSET_M,
  PIT_SCALE,
} from "../../config/constants";
import { egoOnlyLabels, labelledCars } from "../../lib/labels";
import { monotoneCubic, unwrapProgress } from "../../lib/progress";
import { useReplayStore } from "../../stores/replayStore";
import CircuitRibbon, { useRibbon } from "../circuit/CircuitRibbon";
import CarInstances, { type CarMeshRefs } from "./CarInstances";
import CarLabels from "./CarLabels";

// what the scene needs from a playback store: View 2 hands the replay singleton,
// View 5 the live buffer store, View 6's panes share one clock and never tick
export interface PlaybackSlice {
  playheadLap: number;
  selectedCarId: number | null;
  selectCar(id: number | null): void;
  tick(deltaS: number, nominalLapS: number, maxLap: number): void;
}

export interface PlaybackStore {
  <T>(selector: (state: PlaybackSlice) => T): T;
  getState(): PlaybackSlice;
}

interface ReplaySceneProps {
  detail: CircuitDetail;
  gltfUrl: string;
  frames: LapFrame[];
  nominalLapS: number;
  store?: PlaybackStore;
  driveClock?: boolean; // View 6 mounts two scenes on one clock: exactly one driver
  labelPolicy?: "podium" | "ego";
  egoBadge?: string | null;
}

interface CarTrack {
  id: number;
  progressAt(lap: number): number;
}

// frames arrive lap-quantised; a lap playhead maps to the frame index holding it
function frameIndexAt(playheadLap: number, frames: LapFrame[]): number {
  return Math.min(Math.max(Math.ceil(playheadLap) - 1, 0), frames.length - 1);
}

function buildTracks(frames: LapFrame[]): CarTrack[] {
  const laps = frames.map((frame) => frame.lap);
  return frames[0].cars.map((_, carId) => {
    const fractions = frames.map((frame) => frame.cars[carId].s_track);
    return { id: carId, progressAt: monotoneCubic(laps, unwrapProgress(fractions)) };
  });
}

export default function ReplayScene({
  detail,
  gltfUrl,
  frames,
  nominalLapS,
  store = useReplayStore,
  driveClock = true,
  labelPolicy = "podium",
  egoBadge = "agent",
}: ReplaySceneProps) {
  const ribbon = useRibbon(gltfUrl);
  const body = useRef<InstancedMesh | null>(null);
  const fins = useRef<InstancedMesh | null>(null);
  const sprites = useRef<InstancedMesh | null>(null);
  const refs: CarMeshRefs = { body, detail: fins, sprites };

  const positionsNow = useRef(new Map<number, [number, number, number]>());
  const tracks = useMemo(() => {
    positionsNow.current.clear(); // a 20-car run must not label a ghost from a 22-car one
    return buildTracks(frames);
  }, [frames]);
  const maxLap = frames[frames.length - 1].lap;
  const lapLength = detail.lap_length_m ?? ribbon.centreline.total;
  const [cx, cy, cz] = ribbon.centre;

  const scratch = useRef({
    carrier: new Object3D(),
    camLocal: new Vector3(),
    billboard: new Quaternion(),
    forward: new Vector3(0, 1, 0),
    heading: new Vector3(),
    aside: new Vector3(),
    up: new Vector3(0, 0, 1),
    position: new Vector3(),
  });

  // once per lap, not per frame: the DOM label set follows the lap the playhead
  // is in, and the frame loop reads the memoised Set through a ref
  const labelLapIndex = store((state) => frameIndexAt(state.playheadLap, frames));
  const selectedCarId = store((state) => state.selectedCarId);
  const selectCar = store((state) => state.selectCar);
  const shownLabels = useMemo(
    () =>
      labelPolicy === "ego"
        ? egoOnlyLabels(frames[labelLapIndex].cars, selectedCarId)
        : labelledCars(frames[labelLapIndex].cars, selectedCarId),
    [frames, labelLapIndex, selectedCarId, labelPolicy],
  );
  const labelled = useMemo(() => new Set(shownLabels), [shownLabels]);
  const labelledRef = useRef(labelled);
  labelledRef.current = labelled;

  useFrame(({ camera }, delta) => {
    if (driveClock) store.getState().tick(delta, nominalLapS, maxLap);
    const { playheadLap } = store.getState();

    const bodyMesh = body.current;
    const finMesh = fins.current;
    const spriteMesh = sprites.current;
    const parent = bodyMesh?.parent ?? null;
    if (bodyMesh === null || finMesh === null || spriteMesh === null || parent === null) return;

    const { carrier, camLocal, billboard, forward, heading, aside, up, position } =
      scratch.current;
    parent.worldToLocal(camLocal.copy(camera.position));
    // billboard sprites in local space: undo the parent's world rotation, keep the camera's
    parent.getWorldQuaternion(billboard).invert().multiply(camera.quaternion);

    const atFrame = frames[frameIndexAt(playheadLap, frames)];
    const labelled = labelledRef.current;

    for (const track of tracks) {
      const progress = track.progressAt(playheadLap);
      const s_m = (((progress % 1) + 1) % 1) * lapLength;
      const [x, y, z] = ribbon.centreline.sampleAt(s_m);
      const [tx, ty, tz] = ribbon.centreline.tangentAt(s_m);
      heading.set(tx, ty, tz);
      position.set(x - cx, y - cy, z - cz);

      const inPit = atFrame.cars[track.id]?.in_pit ?? false;
      if (inPit) {
        // no pit spline exists (F04 gap, plan divergence 3): pull aside from the
        // racing line and shrink; the transport caption owns the honesty
        aside.copy(up).cross(heading).normalize();
        position.addScaledVector(aside, PIT_LATERAL_OFFSET_M);
      }

      carrier.position.copy(position);
      carrier.quaternion.setFromUnitVectors(forward, heading);
      carrier.scale.setScalar(inPit ? PIT_SCALE : 1);
      carrier.updateMatrix();
      bodyMesh.setMatrixAt(track.id, carrier.matrix);

      const nearEnough = camLocal.distanceTo(position) < LOD_DISTANCE_M;
      if (!nearEnough) carrier.scale.setScalar(0);
      carrier.updateMatrix();
      finMesh.setMatrixAt(track.id, carrier.matrix);

      carrier.position.set(position.x, position.y, position.z + LABEL_HEIGHT_M);
      carrier.quaternion.copy(billboard);
      carrier.scale.setScalar(nearEnough && !labelled.has(track.id) ? 1 : 0);
      carrier.updateMatrix();
      spriteMesh.setMatrixAt(track.id, carrier.matrix);

      positionsNow.current.set(track.id, [position.x, position.y, position.z]);
    }

    bodyMesh.instanceMatrix.needsUpdate = true;
    finMesh.instanceMatrix.needsUpdate = true;
    spriteMesh.instanceMatrix.needsUpdate = true;
  });

  return (
    <group>
      <group position={[-cx, -cy, -cz]}>
        <CircuitRibbon detail={detail} ribbon={ribbon} withCornerMarkers={false} />
      </group>
      {/* car matrices are written in recentred coordinates already */}
      <CarInstances
        count={tracks.length}
        refs={refs}
        onSelect={(carId) => selectCar(carId === selectedCarId ? null : carId)}
      />
      <CarLabels
        cars={frames[labelLapIndex].cars}
        labelledIds={shownLabels}
        egoBadge={egoBadge}
        positionOf={(carId) => positionsNow.current.get(carId) ?? [0, 0, 0]}
      />
    </group>
  );
}
