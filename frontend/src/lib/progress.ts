// From per-lap fractions to smooth car motion. The frames give each car one
// s_track snapshot per lap, folded mod 1 (frames.py); unwrapping assumes the true
// per-lap advance sits in (0.5, 1.5) laps, which holds for anything still racing —
// beyond that a lapped car folds onto its visual position, and the UI already
// labels mid-lap motion illustrative. The interpolant is Fritsch-Carlson monotone
// cubic: unlike Catmull-Rom it cannot overshoot, so a car never drives backwards
// between knots.

export function unwrapProgress(sByLap: number[]): number[] {
  if (sByLap.length === 0) return [];
  const unwrapped = [sByLap[0]];
  for (let lap = 1; lap < sByLap.length; lap++) {
    const delta = sByLap[lap] - sByLap[lap - 1];
    unwrapped.push(unwrapped[lap - 1] + delta - Math.round(delta) + 1);
  }
  return unwrapped;
}

export function monotoneCubic(xs: number[], ys: number[]): (x: number) => number {
  const n = xs.length;
  if (n === 1) return () => ys[0];

  const h: number[] = [];
  const slope: number[] = [];
  for (let i = 0; i < n - 1; i++) {
    h.push(xs[i + 1] - xs[i]);
    slope.push((ys[i + 1] - ys[i]) / h[i]);
  }

  // endpoint tangents take the one-sided slope; interior ones average unless the
  // slopes disagree in sign or either is flat, which forces a flat tangent
  const tangent: number[] = [slope[0]];
  for (let i = 1; i < n - 1; i++) {
    tangent.push(slope[i - 1] * slope[i] <= 0 ? 0 : (slope[i - 1] + slope[i]) / 2);
  }
  tangent.push(slope[n - 2]);

  // Fritsch-Carlson: pull any tangent pair outside the monotone circle back onto it
  for (let i = 0; i < n - 1; i++) {
    if (slope[i] === 0) {
      tangent[i] = 0;
      tangent[i + 1] = 0;
      continue;
    }
    const a = tangent[i] / slope[i];
    const b = tangent[i + 1] / slope[i];
    const radius = a * a + b * b;
    if (radius > 9) {
      const scale = 3 / Math.sqrt(radius);
      tangent[i] = scale * a * slope[i];
      tangent[i + 1] = scale * b * slope[i];
    }
  }

  return (x: number) => {
    if (x <= xs[0]) return ys[0];
    if (x >= xs[n - 1]) return ys[n - 1];

    let i = n - 2;
    for (let knot = 1; knot < n; knot++) {
      if (xs[knot] > x) {
        i = knot - 1;
        break;
      }
    }
    const t = (x - xs[i]) / h[i];
    const t2 = t * t;
    const t3 = t2 * t;
    return (
      (2 * t3 - 3 * t2 + 1) * ys[i] +
      (t3 - 2 * t2 + t) * h[i] * tangent[i] +
      (-2 * t3 + 3 * t2) * ys[i + 1] +
      (t3 - t2) * h[i] * tangent[i + 1]
    );
  };
}
