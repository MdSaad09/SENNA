// The ribbon and its zone overlays, built from the raw GLB POSITION array rather
// than by mounting gltf.scene — the geometry here is ours (an effect below
// disposes it; R3F only auto-disposes declaratively created children), and drei's
// GLTF cache never fights React over lifetimes. Harvest has no zone data of its
// own (plan divergence 2): it renders as a narrower strip over the braking zones,
// and the legend labels that choice stylised.

import { useGLTF } from "@react-three/drei";
import { useEffect, useMemo } from "react";
import { BufferAttribute, BufferGeometry, DoubleSide, Group, Mesh } from "three";

import type { CircuitDetail } from "../../api/types";
import { ANNOTATION_LIFT_M } from "../../config/constants";
import { buildCentreline, type Centreline } from "../../lib/centreline";
import { buildStrip, type StripGeometry, type StripZone } from "../../lib/ribbonStrips";
import CornerMarkers from "./CornerMarkers";
import { SCENE } from "../../config/palette";

// stylised — zone tints: braking amber, X-mode violet, harvest teal over braking;
// exported so the Legend's swatches can never drift from the canvas
export const BRAKING_TINT = SCENE.braking;
export const XMODE_TINT = SCENE.xmode;
export const HARVEST_TINT = SCENE.harvestZone;
const DECK_TINT = SCENE.deck;

// stylised — overlay opacities: braking and X-mode translucent so the deck reads
// through, harvest nearly solid because it is the narrowest strip
const BRAKING_OPACITY = 0.55;
const XMODE_OPACITY = 0.5;
const HARVEST_OPACITY = 0.8;

// stylised — strip widths as ribbon fractions; harvest sits inside its braking zone
const ZONE_WIDTH_FRACTION = 0.92;
const HARVEST_WIDTH_FRACTION = 0.45;
// stylised — stacking order above the deck in ANNOTATION_LIFT_M steps: zones,
// then harvest, then the start line on top
const HARVEST_LIFT_STEPS = 2;
const START_LINE_LIFT_STEPS = 3;
// stylised — the start line is a short full-width band at s = 0
const START_LINE_LENGTH_M = 8;

export interface RibbonFrame {
  positions: Float32Array;
  centreline: Centreline;
  centre: [number, number, number];
  /** bounding-sphere radius about `centre`, in metres — what FitCamera frames against.
   *  A sphere rather than a box because circuits are not axis-aligned and Monaco read
   *  half the size of Spa under a width-only fit. */
  radius: number;
}

function ribbonPositions(gltf: unknown): Float32Array {
  // the vitest drei mock hands positions back directly; a real GLTF wraps them in
  // a one-mesh scene (senna/circuits/export.py)
  const direct = (gltf as { positions?: unknown }).positions;
  if (direct instanceof Float32Array) return direct;

  let found: Float32Array | null = null;
  (gltf as { scene: Group }).scene.traverse((node) => {
    if (found === null && (node as Mesh).isMesh) {
      const attribute = (node as Mesh).geometry.getAttribute("position");
      found = attribute.array as Float32Array;
    }
  });
  if (found === null) {
    throw new Error("ribbon GLB carries no mesh positions — rebuild with make circuits");
  }
  return found;
}

/** Load the GLB and rebuild what the frontend needs from it: the centreline and a
 * recentring offset (FastF1 local coordinates sit far from the origin). */
export function useRibbon(gltfUrl: string): RibbonFrame {
  const gltf = useGLTF(gltfUrl);
  return useMemo(() => {
    const positions = ribbonPositions(gltf);
    const centreline = buildCentreline(positions);
    let minX = Infinity, minY = Infinity, minZ = Infinity;
    let maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity;
    for (let i = 0; i < positions.length; i += 3) {
      minX = Math.min(minX, positions[i]); maxX = Math.max(maxX, positions[i]);
      minY = Math.min(minY, positions[i + 1]); maxY = Math.max(maxY, positions[i + 1]);
      minZ = Math.min(minZ, positions[i + 2]); maxZ = Math.max(maxZ, positions[i + 2]);
    }
    return {
      positions,
      centreline,
      centre: [(minX + maxX) / 2, (minY + maxY) / 2, (minZ + maxZ) / 2],
      radius: Math.hypot(maxX - minX, maxY - minY, maxZ - minZ) / 2,
    };
  }, [gltf]);
}

function ribbonGeometry(positions: Float32Array): BufferGeometry {
  const stations = positions.length / 6;
  const indices = new Uint32Array(stations * 6);
  for (let i = 0; i < stations; i++) {
    const left = i * 2;
    const nextLeft = ((i + 1) % stations) * 2;
    indices.set([left, left + 1, nextLeft, left + 1, nextLeft + 1, nextLeft], i * 6);
  }
  const geometry = new BufferGeometry();
  geometry.setAttribute("position", new BufferAttribute(positions.slice(), 3));
  geometry.setIndex(new BufferAttribute(indices, 1));
  geometry.computeVertexNormals();
  return geometry;
}

function stripGeometry(built: StripGeometry): BufferGeometry {
  const geometry = new BufferGeometry();
  geometry.setAttribute("position", new BufferAttribute(built.positions, 3));
  geometry.setIndex(new BufferAttribute(built.indices, 1));
  geometry.computeVertexNormals();
  return geometry;
}

interface CircuitRibbonProps {
  detail: CircuitDetail;
  ribbon: RibbonFrame;
  withCornerMarkers?: boolean;
}

export default function CircuitRibbon({
  detail,
  ribbon,
  withCornerMarkers = true,
}: CircuitRibbonProps) {
  const { positions, centreline } = ribbon;

  const geometries = useMemo(() => {
    const zoneStrip = (zones: StripZone[], fraction: number, lift: number) =>
      stripGeometry(buildStrip(centreline, zones, { lift_m: lift, width_fraction: fraction }));

    const braking = detail.braking_zones ?? [];
    const xmode = detail.xmode_sections ?? [];
    return {
      deck: ribbonGeometry(positions),
      braking: zoneStrip(braking, ZONE_WIDTH_FRACTION, ANNOTATION_LIFT_M),
      // harvest happens under braking (MGU-K), so its stylised strip rides the
      // same zones, narrower and a step higher so both stay visible
      harvest: zoneStrip(braking, HARVEST_WIDTH_FRACTION, ANNOTATION_LIFT_M * HARVEST_LIFT_STEPS),
      xmode: zoneStrip(xmode, ZONE_WIDTH_FRACTION, ANNOTATION_LIFT_M),
      startLine: zoneStrip(
        [{ start_m: 0, end_m: START_LINE_LENGTH_M }],
        1,
        ANNOTATION_LIFT_M * START_LINE_LIFT_STEPS,
      ),
    };
  }, [positions, centreline, detail]);

  // prop-attached geometries are outside R3F's auto-dispose; free the GPU buffers
  // when the circuit changes or the route unmounts
  useEffect(
    () => () => {
      for (const geometry of Object.values(geometries)) geometry.dispose();
    },
    [geometries],
  );

  return (
    <group>
      <mesh geometry={geometries.deck}>
        <meshStandardMaterial color={DECK_TINT} side={DoubleSide} />
      </mesh>
      <mesh geometry={geometries.braking}>
        <meshBasicMaterial
          color={BRAKING_TINT}
          transparent
          opacity={BRAKING_OPACITY}
          side={DoubleSide}
        />
      </mesh>
      <mesh geometry={geometries.harvest}>
        <meshBasicMaterial
          color={HARVEST_TINT}
          transparent
          opacity={HARVEST_OPACITY}
          side={DoubleSide}
        />
      </mesh>
      <mesh geometry={geometries.xmode}>
        <meshBasicMaterial
          color={XMODE_TINT}
          transparent
          opacity={XMODE_OPACITY}
          side={DoubleSide}
        />
      </mesh>
      <mesh geometry={geometries.startLine}>
        <meshBasicMaterial color={SCENE.cornerMarker} side={DoubleSide} />
      </mesh>
      {withCornerMarkers && detail.corners !== null && (
        <CornerMarkers centreline={centreline} corners={detail.corners} />
      )}
    </group>
  );
}
