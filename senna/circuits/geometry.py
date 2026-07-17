"""Ribbon geometry — the pure-numpy core of the F04 pipeline (spec 5.10.1).

The algorithm splits cleanly: resample the raw centreline by arc length, smooth
it, carry rotation-minimising frames along it (kept periodic on a closed loop),
then extrude a ribbon whose half-width is clamped to the local curve radius. The
clamp is what stops a sub-6 m hairpin — Monaco, Hungary — from folding its inner
edge (E-17). Everything here is numpy in, numpy out — no FastF1, no pandas, no
I/O — so the invariants hold against synthetic hairpins and real circuits alike.
"""

import numpy as np


def resample_by_arc_length(points: np.ndarray, spacing_m: float) -> np.ndarray:
    """Resample an open polyline to uniform arc-length spacing (5.10.1 item 2)."""
    step = np.linalg.norm(np.diff(points, axis=0), axis=1)
    arc = np.concatenate([[0.0], np.cumsum(step)])
    targets = np.arange(0.0, arc[-1], spacing_m)
    return np.column_stack([np.interp(targets, arc, points[:, axis]) for axis in range(3)])


def close_loop(points: np.ndarray) -> np.ndarray:
    """Append the first point so the ribbon forms a closed ring (5.10.1 item 2)."""
    if np.allclose(points[0], points[-1]):
        return points
    return np.vstack([points, points[0]])


def savgol_smooth(values: np.ndarray, window: int, polyorder: int, *, closed: bool) -> np.ndarray:
    """Savitzky-Golay along axis 0. A closed loop wraps; an open lap uses edge fits."""
    from scipy.signal import savgol_filter

    mode = "wrap" if closed else "interp"
    return savgol_filter(values, window, polyorder, axis=0, mode=mode)


def rotation_minimising_frames(
    points: np.ndarray, *, closed: bool
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Parallel-transport frames by double reflection (Wang et al. 2008).

    Frenet frames twist at inflection points and hairpins (E-17); this carries a
    reference normal along the curve with the least possible rotation, so the
    extruded ribbon never flips. A closed circuit accumulates a holonomy angle
    around the loop; when `closed`, that residual twist is spread back over the
    stations so the frame is periodic and the start-finish quad has no seam.
    Returns unit (tangents, normals, binormals).
    """
    tangents = _unit(_periodic_gradient(points) if closed else np.gradient(points, axis=0))
    normals = np.empty_like(points)
    normals[0] = _seed_normal(tangents[0])
    for i in range(len(points) - 1):
        normals[i + 1] = _transport(
            normals[i], tangents[i], tangents[i + 1], points[i + 1] - points[i]
        )
    normals = _unit(normals)

    if closed:
        wrapped = _transport(normals[-1], tangents[-1], tangents[0], points[0] - points[-1])
        holonomy = _signed_angle(wrapped, normals[0], tangents[0])
        spread = holonomy * np.arange(len(points)) / len(points)
        turned = [_rotate_about(n, t, a) for n, t, a in zip(normals, tangents, spread, strict=True)]
        normals = _unit(np.array(turned))

    binormals = _unit(np.cross(tangents, normals))
    return tangents, normals, binormals


def curve_radius(points: np.ndarray, *, closed: bool) -> np.ndarray:
    """Local radius of curvature at each point via Menger curvature; inf on straights."""
    before = np.roll(points, 1, axis=0) if closed else np.vstack([points[:1], points[:-1]])
    after = np.roll(points, -1, axis=0) if closed else np.vstack([points[1:], points[-1:]])

    side_a = np.linalg.norm(points - before, axis=1)
    side_b = np.linalg.norm(after - points, axis=1)
    side_c = np.linalg.norm(after - before, axis=1)
    area = 0.5 * np.linalg.norm(np.cross(points - before, after - before), axis=1)

    radius = np.full(len(points), np.inf)
    curved = area > 1e-9
    radius[curved] = (side_a[curved] * side_b[curved] * side_c[curved]) / (4.0 * area[curved])
    return radius


def build_ribbon_vertices(
    centreline: np.ndarray,
    lateral: np.ndarray,
    half_width_m: float,
    local_radius: np.ndarray,
    clamp_fraction: float,
) -> np.ndarray:
    """Extrude left/right edges, half-width clamped to local radius (5.10.1 item 4, E-17).

    Returns (N, 2, 3): index 0 is the left edge, index 1 the right. Where the
    curve is tighter than the ribbon is wide, the effective half-width shrinks to
    clamp_fraction x radius, keeping the inner edge on its own side of the centre.
    """
    lateral_unit = _unit(lateral)
    effective_half_width = np.minimum(half_width_m, clamp_fraction * local_radius)
    offset = effective_half_width[:, None] * lateral_unit
    return np.stack([centreline + offset, centreline - offset], axis=1)


def ribbon_self_intersects(vertices: np.ndarray) -> bool:
    """True if either ribbon edge crosses itself in plan view (E-17 unit test)."""
    return _edge_self_intersects(vertices[:, 0, :2]) or _edge_self_intersects(vertices[:, 1, :2])


def _edge_self_intersects(edge_xy: np.ndarray) -> bool:
    # Each segment i is tested against every non-adjacent later segment at once, so
    # the work stays O(n^2) but the Python loop is O(n) — a real circuit is ~2000
    # stations and the naive pair loop takes minutes. A proper crossing needs both
    # endpoint pairs to straddle (strictly opposite orientations); shared endpoints
    # give a zero orientation and so never count, which handles the closed-loop seam.
    starts, ends = edge_xy[:-1], edge_xy[1:]
    for i in range(len(starts) - 2):
        a, b = starts[i], ends[i]
        others_start, others_end = starts[i + 2 :], ends[i + 2 :]
        straddle_ab = _orient(a, b, others_start) * _orient(a, b, others_end) < 0
        straddle_cd = (
            _orient_rows(others_start, others_end, a) * _orient_rows(others_start, others_end, b)
            < 0
        )
        if np.any(straddle_ab & straddle_cd):
            return True
    return False


def _orient(a: np.ndarray, b: np.ndarray, points: np.ndarray) -> np.ndarray:
    # signed area of triangle (a, b, point) for each point in a batch
    return (b[0] - a[0]) * (points[:, 1] - a[1]) - (b[1] - a[1]) * (points[:, 0] - a[0])


def _orient_rows(starts: np.ndarray, ends: np.ndarray, point: np.ndarray) -> np.ndarray:
    # signed area of triangle (segment_start, segment_end, point), one per segment
    return (ends[:, 0] - starts[:, 0]) * (point[1] - starts[:, 1]) - (ends[:, 1] - starts[:, 1]) * (
        point[0] - starts[:, 0]
    )


def lap_length_m(centreline: np.ndarray, *, closed: bool) -> float:
    """Centreline arc length; adds the closing segment if the loop is not already sealed."""
    total = float(np.linalg.norm(np.diff(centreline, axis=0), axis=1).sum())
    if closed and not np.allclose(centreline[0], centreline[-1]):
        total += float(np.linalg.norm(centreline[0] - centreline[-1]))
    return total


def within_tolerance(measured_m: float, official_m: float, tolerance_pct: float) -> bool:
    """Lap length must match the official figure within tolerance (5.10.1 item 7)."""
    return abs(measured_m - official_m) / official_m <= tolerance_pct / 100.0


def _unit(vectors: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vectors, axis=-1, keepdims=True)
    return vectors / np.maximum(norm, 1e-12)


def _seed_normal(tangent: np.ndarray) -> np.ndarray:
    # any unit vector orthogonal to the first tangent; pick the world axis least
    # aligned with it so the cross product is well conditioned
    axis = np.eye(3)[np.argmin(np.abs(tangent))]
    return _unit(np.cross(tangent, axis))


def _transport(normal: np.ndarray, tangent: np.ndarray, next_tangent: np.ndarray, step: np.ndarray):
    # one double-reflection step: reflect the frame across the segment, then across
    # the bisector that maps the reflected tangent onto the next one (Wang 2008)
    reflected_normal = _reflect(normal, step)
    reflected_tangent = _reflect(tangent, step)
    return _reflect(reflected_normal, next_tangent - reflected_tangent)


def _periodic_gradient(points: np.ndarray) -> np.ndarray:
    # central difference that wraps, so the tangent at the seam is not one-sided
    return (np.roll(points, -1, axis=0) - np.roll(points, 1, axis=0)) / 2.0


def _signed_angle(start: np.ndarray, end: np.ndarray, axis: np.ndarray) -> float:
    start, end, axis = _unit(start), _unit(end), _unit(axis)
    return float(np.arctan2(np.cross(start, end) @ axis, start @ end))


def _rotate_about(vector: np.ndarray, axis: np.ndarray, angle: float) -> np.ndarray:
    axis = _unit(axis)
    cos, sin = np.cos(angle), np.sin(angle)
    return vector * cos + np.cross(axis, vector) * sin + axis * (axis @ vector) * (1.0 - cos)


def _reflect(vector: np.ndarray, mirror: np.ndarray) -> np.ndarray:
    denom = float(mirror @ mirror)
    if denom < 1e-18:
        return vector
    return vector - (2.0 * (mirror @ vector) / denom) * mirror
