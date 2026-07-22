// The F04 GLB carries only the ribbon triangles, so the centreline is rebuilt here
// from its vertex layout: station i keeps its left edge at vertex 2i and its right
// edge at 2i + 1, and the midpoint of each pair is the centreline point. Everything
// downstream — car placement, zone strips, corner markers — samples this by arc
// length, because meta.json speaks in distance_m (its corner x/y are decimetres and
// deliberately unused).

export interface Centreline {
  stations: number;
  cumS: Float32Array;
  total: number;
  sampleAt(s_m: number): [number, number, number];
  tangentAt(s_m: number): [number, number, number];
  leftAt(s_m: number): [number, number, number];
  rightAt(s_m: number): [number, number, number];
}

type Vec3 = [number, number, number];

function ringLerp(points: Vec3[], cumS: Float32Array, total: number, s_m: number): Vec3 {
  const s = ((s_m % total) + total) % total;
  const n = points.length;

  // binary search for the segment holding s — the replay samples every car every
  // frame, and a linear scan over ~2700 stations is the loop's biggest CPU item
  let lo = 0;
  let hi = n - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (cumS[mid] <= s) lo = mid;
    else hi = mid - 1;
  }
  const i = lo; // the last segment (i === n - 1) closes the ring
  const from = points[i];
  const to = points[(i + 1) % n];
  const segmentStart = cumS[i];
  const segmentLength = (i === n - 1 ? total : cumS[i + 1]) - segmentStart;
  const t = segmentLength > 0 ? (s - segmentStart) / segmentLength : 0;
  return [
    from[0] + t * (to[0] - from[0]),
    from[1] + t * (to[1] - from[1]),
    from[2] + t * (to[2] - from[2]),
  ];
}

export function buildCentreline(positions: Float32Array): Centreline {
  const stations = positions.length / 6;
  const centres: Vec3[] = [];
  const lefts: Vec3[] = [];
  const rights: Vec3[] = [];

  for (let i = 0; i < stations; i++) {
    const l = i * 6;
    const r = l + 3;
    lefts.push([positions[l], positions[l + 1], positions[l + 2]]);
    rights.push([positions[r], positions[r + 1], positions[r + 2]]);
    centres.push([
      (positions[l] + positions[r]) / 2,
      (positions[l + 1] + positions[r + 1]) / 2,
      (positions[l + 2] + positions[r + 2]) / 2,
    ]);
  }

  const cumS = new Float32Array(stations);
  for (let i = 1; i < stations; i++) {
    const [ax, ay, az] = centres[i - 1];
    const [bx, by, bz] = centres[i];
    cumS[i] = cumS[i - 1] + Math.hypot(bx - ax, by - ay, bz - az);
  }
  const [lx, ly, lz] = centres[stations - 1];
  const [fx, fy, fz] = centres[0];
  const total = cumS[stations - 1] + Math.hypot(fx - lx, fy - ly, fz - lz);

  return {
    stations,
    cumS,
    total,
    sampleAt: (s_m) => ringLerp(centres, cumS, total, s_m),
    leftAt: (s_m) => ringLerp(lefts, cumS, total, s_m),
    rightAt: (s_m) => ringLerp(rights, cumS, total, s_m),
    tangentAt: (s_m) => {
      // central difference over a short arc step: cheap, and smooth enough for
      // pointing a car along the track
      const step = Math.max(total * 1e-4, 0.5);
      const ahead = ringLerp(centres, cumS, total, s_m + step);
      const behind = ringLerp(centres, cumS, total, s_m - step);
      const dx = ahead[0] - behind[0];
      const dy = ahead[1] - behind[1];
      const dz = ahead[2] - behind[2];
      const norm = Math.hypot(dx, dy, dz) || 1;
      return [dx / norm, dy / norm, dz / norm];
    },
  };
}
