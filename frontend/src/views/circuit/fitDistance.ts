// The camera fit, as a pure function so it can be tested. Inside FitCamera it sat behind
// a `useThree()` guard that the jsdom mock short-circuits, so the only new maths in F23
// had no test at all.

/** How far back a perspective camera must sit for a sphere of `radius` to occupy `fill`
 *  of the tighter viewport dimension. A landscape panel is bound by its height, a
 *  portrait one by its width, so the binding half-angle is the smaller of the two. */
export function fitDistance(
  radius: number,
  fovDeg: number,
  aspect: number,
  fill: number,
): number {
  if (radius <= 0 || fill <= 0) return 0;
  const halfVertical = (fovDeg * Math.PI) / 360;
  const halfHorizontal = Math.atan(Math.tan(halfVertical) * aspect);
  const half = Math.min(halfVertical, halfHorizontal);
  return radius / (fill * Math.sin(half));
}
