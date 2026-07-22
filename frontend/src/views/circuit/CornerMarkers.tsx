// Corner posts placed by distance_m along the reconstructed centreline — the
// meta.json corner x/y are raw FastF1 decimetres at 10x the mesh scale, so arc
// length is the only trustworthy anchor. One InstancedMesh for the posts, one
// drei Text per number (View 1 is static and sits far under the replay budget).

import { Text } from "@react-three/drei";
import { useLayoutEffect, useRef } from "react";
import { InstancedMesh, Object3D } from "three";

import type { CircuitCorner } from "../../api/types";
import type { Centreline } from "../../lib/centreline";

// stylised — marker post proportions and the number's hover height
const POST_RADIUS_M = 1.2;
const POST_HEIGHT_M = 6;
const NUMBER_HEIGHT_M = 10;
const NUMBER_SIZE_M = 8;

export default function CornerMarkers({
  centreline,
  corners,
}: {
  centreline: Centreline;
  corners: CircuitCorner[];
}) {
  const posts = useRef<InstancedMesh>(null);

  useLayoutEffect(() => {
    const mesh = posts.current;
    if (mesh === null) return;
    const scratch = new Object3D();
    corners.forEach((corner, index) => {
      const [x, y, z] = centreline.sampleAt(corner.distance_m);
      scratch.position.set(x, y, z + POST_HEIGHT_M / 2);
      scratch.rotation.set(Math.PI / 2, 0, 0); // cylinder axis onto the Z-up deck
      scratch.updateMatrix();
      mesh.setMatrixAt(index, scratch.matrix);
    });
    mesh.instanceMatrix.needsUpdate = true;
  }, [centreline, corners]);

  return (
    <group>
      <instancedMesh ref={posts} args={[undefined, undefined, corners.length]} frustumCulled={false}>
        <cylinderGeometry args={[POST_RADIUS_M, POST_RADIUS_M, POST_HEIGHT_M, 8]} />
        <meshStandardMaterial color="#e5e5e5" />
      </instancedMesh>
      {corners.map((corner) => {
        const [x, y, z] = centreline.sampleAt(corner.distance_m);
        return (
          <Text
            key={corner.number}
            position={[x, y, z + NUMBER_HEIGHT_M]}
            rotation={[Math.PI / 2, 0, 0]}
            fontSize={NUMBER_SIZE_M}
            color="#fafafa"
            anchorX="center"
            anchorY="middle"
          >
            {corner.number}
          </Text>
        );
      })}
    </group>
  );
}
