// Frame the ribbon so it fills the view, whatever circuit it is.
//
// Before F23 the camera sat at a fixed [0, 900, 900] for every circuit, so Monaco (3.3 km,
// tightly wound) rendered about half the size of Spa (7.0 km) and the reference screenshot
// shows the result: a small shape adrift in a large dark panel. Fitting to the loaded
// bounds fixes every circuit at once instead of picking a distance that suits one.

import { useThree } from "@react-three/fiber";
import { useEffect } from "react";
import type { PerspectiveCamera } from "three";

import { CAMERA, RIBBON_VIEWPORT_FILL } from "../../config/constants";

/** The opening pose's direction, kept so the reframe changes the distance and nothing
 *  else — the three-quarter view is a deliberate look, not an accident of the number. */
const DIRECTION = (() => {
  const [x, y, z] = CAMERA.position;
  const length = Math.hypot(x, y, z);
  return [x / length, y / length, z / length] as const;
})();

export default function FitCamera({ radius }: { radius: number }) {
  const { camera, size } = useThree();

  useEffect(() => {
    // the R3F mock returns a bare {} in jsdom; nothing to frame there
    if (camera === undefined || size === undefined || radius <= 0) return;

    const aspect = size.height === 0 ? 1 : size.width / size.height;
    const halfVertical = ((camera as PerspectiveCamera).fov * Math.PI) / 360;
    const halfHorizontal = Math.atan(Math.tan(halfVertical) * aspect);
    // a portrait panel is bound by its width, a landscape one by its height
    const half = Math.min(halfVertical, halfHorizontal);
    const distance = radius / (RIBBON_VIEWPORT_FILL * Math.sin(half));

    camera.position.set(
      DIRECTION[0] * distance,
      DIRECTION[1] * distance,
      DIRECTION[2] * distance,
    );
    camera.lookAt(0, 0, 0);
    camera.updateProjectionMatrix();
  }, [camera, size, radius]);

  return null;
}
