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
import {
  ANNOTATION_LIFT_M,
  CAMERA,
  RIBBON_WIDTH_EXAGGERATION,
} from "../../config/constants";
import { buildCentreline, type Centreline } from "../../lib/centreline";
import { buildStrip, type StripGeometry, type StripZone } from "../../lib/ribbonStrips";
import { SCENE } from "../../config/palette";
import CornerMarkers from "./CornerMarkers";

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
  /** the radius FitCamera frames against, in metres: the circuit's silhouette as seen
   *  down the opening camera direction — the furthest any vertex sits from the view axis.
   *
   *  Not a bounding sphere. A circuit is a flat, irregular curve and the camera looks at
   *  it from 45 degrees, so a sphere around it is mostly empty air: Albert Park framed to
   *  0.82 of a sphere filled about 40% of the panel, which is the "model renders too
   *  small" complaint the fit was supposed to answer. */
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
    const positions = widenRibbon(ribbonPositions(gltf));
    const centreline = buildCentreline(positions);
    let minX = Infinity, minY = Infinity, minZ = Infinity;
    let maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity;
    for (let i = 0; i < positions.length; i += 3) {
      minX = Math.min(minX, positions[i]); maxX = Math.max(maxX, positions[i]);
      minY = Math.min(minY, positions[i + 1]); maxY = Math.max(maxY, positions[i + 1]);
      minZ = Math.min(minZ, positions[i + 2]); maxZ = Math.max(maxZ, positions[i + 2]);
    }
    const [cx, cy, cz] = [(minX + maxX) / 2, (minY + maxY) / 2, (minZ + maxZ) / 2];
    return {
      positions,
      centreline,
      centre: [cx, cy, cz],
      radius: silhouetteRadius(positions, [cx, cy, cz]),
    };
  }, [gltf]);
}

/** The furthest any ribbon vertex sits from the axis through `centre` along the opening
 *  camera direction — i.e. the radius of the circuit's outline as the camera first sees
 *  it, with the foreshortening of the 45-degree view already taken out. */
function silhouetteRadius(positions: Float32Array, centre: [number, number, number]): number {
  const [dx, dy, dz] = CAMERA.position;
  const length = Math.hypot(dx, dy, dz) || 1;
  const [ux, uy, uz] = [dx / length, dy / length, dz / length];

  let furthest = 0;
  for (let i = 0; i < positions.length; i += 3) {
    const px = positions[i] - centre[0];
    const py = positions[i + 1] - centre[1];
    const pz = positions[i + 2] - centre[2];
    const along = px * ux + py * uy + pz * uz;
    // Pythagoras on the component perpendicular to the view axis
    const perpendicular = Math.max(px * px + py * py + pz * pz - along * along, 0);
    furthest = Math.max(furthest, perpendicular);
  }
  return Math.sqrt(furthest);
}

/** Push each station's two edge vertices apart from their midpoint. The centreline is
 *  the midpoint, so it is untouched — only the drawn width changes, and the annotation
 *  strips built from these positions widen with it. */
function widenRibbon(positions: Float32Array): Float32Array {
  const widened = positions.slice();
  for (let i = 0; i < widened.length; i += 6) {
    for (let axis = 0; axis < 3; axis++) {
      const left = widened[i + axis];
      const right = widened[i + 3 + axis];
      const centre = (left + right) / 2;
      widened[i + axis] = centre + (left - centre) * RIBBON_WIDTH_EXAGGERATION;
      widened[i + 3 + axis] = centre + (right - centre) * RIBBON_WIDTH_EXAGGERATION;
    }
  }
  return widened;
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
  /** braking, harvest and X-mode strips. They are what View 1 is *for*; under a race they
   *  paint the whole lap amber and violet and the cars have to compete with them for
   *  attention, so the replay and live views draw the deck bare. */
  withZones?: boolean;
}

export default function CircuitRibbon({
  detail,
  ribbon,
  withCornerMarkers = true,
  withZones = true,
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
      {withZones && (
        <>
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
        </>
      )}
      <mesh geometry={geometries.startLine}>
        <meshBasicMaterial color={SCENE.cornerMarker} side={DoubleSide} />
      </mesh>
      {withCornerMarkers && detail.corners !== null && (
        <CornerMarkers centreline={centreline} corners={detail.corners} />
      )}
    </group>
  );
}
