// A hand-checkable ribbon: a 10 m square walked counter-clockwise from the origin,
// one station per corner, closing back to the start. The vertex layout mirrors the
// GLB POSITION attribute the F04 builder emits — station i keeps its left edge at
// vertex 2i and its right edge at vertex 2i + 1, as x/y/z triplets. The left edge
// sits 1 m outward along the corner diagonal, the right edge 1 m inward, so every
// pair's midpoint is exactly the centreline corner and the ribbon is 2 m wide.

const DIAG = Math.SQRT1_2; // a unit outward diagonal has |x| = |y| = 1/sqrt(2)

export const squareCentres: [number, number, number][] = [
  [0, 0, 0],
  [10, 0, 0],
  [10, 10, 0],
  [0, 10, 0],
];

const outwardDiagonals: [number, number][] = [
  [-DIAG, -DIAG],
  [DIAG, -DIAG],
  [DIAG, DIAG],
  [-DIAG, DIAG],
];

export const squareRibbonPositions = new Float32Array(
  squareCentres.flatMap(([x, y, z], station) => {
    const [dx, dy] = outwardDiagonals[station];
    return [x + dx, y + dy, z, x - dx, y - dy, z];
  }),
);

// centreline arc length at each station, and the closed-ring total
export const squareCumS = [0, 10, 20, 30];
export const squareTotal = 40;

// What the mocked drei useGLTF hands back. The view never mounts gltf.scene (the
// plan keeps drei's cache away from disposal), so null is honest here.
export const gltfStub = { scene: null as unknown, positions: squareRibbonPositions };
