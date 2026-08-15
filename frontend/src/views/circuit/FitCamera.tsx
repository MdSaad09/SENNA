// Frame the ribbon so it fills the view, whatever circuit it is.
//
// Before F23 the camera sat at a fixed [0, 900, 900] for every circuit, so Monaco (3.3 km,
// tightly wound) rendered about half the size of Spa (7.0 km) and the reference screenshot
// shows the result: a small shape adrift in a large dark panel. Fitting to the loaded
// bounds fixes every circuit at once instead of picking a distance that suits one.

import { useThree } from "@react-three/fiber";
import { useEffect, useRef } from "react";
import type { PerspectiveCamera } from "three";

import { CAMERA, RIBBON_VIEWPORT_FILL } from "../../config/constants";
import { fitDistance } from "./fitDistance";

const OPENING_DIRECTION = CAMERA.position;

export default function FitCamera({ radius }: { radius: number }) {
  const { camera, size } = useThree();
  const framed = useRef<number | null>(null);

  useEffect(() => {
    // the R3F mock returns a bare {} in jsdom; nothing to frame there
    if (camera === undefined || size === undefined) return;

    const distance = fitDistance(
      radius,
      (camera as PerspectiveCamera).fov,
      size.height === 0 ? 1 : size.width / size.height,
      RIBBON_VIEWPORT_FILL,
    );
    if (distance === 0) return;

    // A resize must refit the distance but must NOT reclaim the direction: at the demo's
    // circuit beat the presenter has usually orbited somewhere, and a screen-share layout
    // change would otherwise snap the camera back to the opening three-quarter view
    // mid-sentence. Only a new circuit (a new radius) resets the pose.
    const fresh = framed.current !== radius;
    const from = fresh ? OPENING_DIRECTION : camera.position.toArray();
    const length = Math.hypot(from[0], from[1], from[2]) || 1;

    camera.position.set(
      (from[0] / length) * distance,
      (from[1] / length) * distance,
      (from[2] / length) * distance,
    );
    camera.lookAt(0, 0, 0);
    camera.updateProjectionMatrix();
    framed.current = radius;
  }, [camera, size, radius]);

  return null;
}
