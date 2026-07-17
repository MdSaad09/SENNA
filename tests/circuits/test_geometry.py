from pathlib import Path

import numpy as np
import pytest

from senna.circuits.geometry import (
    build_ribbon_vertices,
    close_loop,
    resample_by_arc_length,
    ribbon_self_intersects,
    rotation_minimising_frames,
    savgol_smooth,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def circle(radius_m, n, *, arc_fraction=1.0):
    theta = np.linspace(0.0, arc_fraction * 2 * np.pi, n)
    return np.column_stack([radius_m * np.cos(theta), radius_m * np.sin(theta), np.zeros(n)])


def test_resample_gives_uniform_2m_spacing():
    dense = circle(radius_m=50.0, n=2000, arc_fraction=0.75)

    resampled = resample_by_arc_length(dense, spacing_m=2.0)

    spacings = np.linalg.norm(np.diff(resampled, axis=0), axis=1)
    # the final remainder segment is allowed to be short; the body must be ~2 m
    assert np.abs(spacings[:-1].mean() - 2.0) < 0.05
    assert spacings[:-1].std() < 0.05


def test_loop_closure_first_last_coincide():
    open_curve = circle(radius_m=30.0, n=400, arc_fraction=0.98)
    assert not np.allclose(open_curve[0], open_curve[-1])

    closed = close_loop(open_curve)

    assert np.allclose(closed[0], closed[-1])


def test_rmf_no_twist_flip_across_hairpin():
    # A 3D S-curve: the y-sine carries an inflection at t = pi and tight curvature at the
    # peaks. Frenet frames flip their normal through the inflection; RMF must not (E-17).
    t = np.linspace(0.2, 2 * np.pi - 0.2, 240)
    centreline = np.column_stack([3.0 * t, 8.0 * np.sin(t), 2.0 * np.sin(0.5 * t)])

    _, normals, _ = rotation_minimising_frames(centreline, closed=False)
    rmf_dots = np.sum(normals[:-1] * normals[1:], axis=1)

    # naive Frenet normal, computed here in the test so the module is not implicated:
    # second derivative of the centreline, normalised. It flips sign at the inflection.
    d2 = np.gradient(np.gradient(centreline, axis=0), axis=0)
    frenet = d2 / np.maximum(np.linalg.norm(d2, axis=1, keepdims=True), 1e-12)
    frenet_dots = np.sum(frenet[:-1] * frenet[1:], axis=1)

    assert frenet_dots.min() < 0.0, "the Frenet baseline should flip, proving RMF is needed"
    assert np.all(rmf_dots > 0.0), "rotation-minimising normals must stay continuous (E-17)"


def test_ribbon_no_self_intersection_synthetic_hairpin():
    # 12 m ribbon extruded along a sub-6 m radius arc: the half-width clamp keeps the
    # inner edge on its own side, so no edge crosses itself (E-17).
    radius_m = 5.0
    theta = np.linspace(0.0, 1.6 * np.pi, 300)
    centreline = np.column_stack(
        [radius_m * np.cos(theta), radius_m * np.sin(theta), np.zeros_like(theta)]
    )
    lateral = np.column_stack([np.cos(theta), np.sin(theta), np.zeros_like(theta)])
    local_radius = np.full(theta.shape, radius_m)

    vertices = build_ribbon_vertices(
        centreline, lateral, half_width_m=12.0, local_radius=local_radius, clamp_fraction=0.9
    )

    assert ribbon_self_intersects(vertices) is False


def test_halfwidth_clamped_to_local_radius():
    radius_m = 3.0
    theta = np.linspace(0.0, np.pi, 200)
    centreline = np.column_stack(
        [radius_m * np.cos(theta), radius_m * np.sin(theta), np.zeros_like(theta)]
    )
    lateral = np.column_stack([np.cos(theta), np.sin(theta), np.zeros_like(theta)])
    local_radius = np.full(theta.shape, radius_m)
    clamp_fraction = 0.9

    vertices = build_ribbon_vertices(
        centreline, lateral, half_width_m=12.0, local_radius=local_radius, clamp_fraction=clamp_fraction
    )

    left, right = vertices[:, 0], vertices[:, 1]
    effective_left = np.linalg.norm(left - centreline, axis=1)
    effective_right = np.linalg.norm(right - centreline, axis=1)
    expected = clamp_fraction * radius_m
    assert np.allclose(effective_left, expected)
    assert np.allclose(effective_right, expected)

    # the inner edge stays strictly inside the centreline arc: it never reaches or crosses it
    inner_radius = np.linalg.norm(right, axis=1)
    assert np.all(inner_radius > 0.0)
    assert np.all(inner_radius < radius_m)


def test_savgol_z_smoothed_harder_than_xy():
    rng = np.random.default_rng(0)
    t = np.linspace(0.0, 2 * np.pi, 400)
    truth = 5.0 * np.sin(t / 4.0)  # low frequency, so the wider window adds little bias
    noisy = truth + rng.normal(0.0, 1.0, size=t.shape)

    smoothed_xy = savgol_smooth(noisy, window=11, polyorder=3, closed=False)
    smoothed_z = savgol_smooth(noisy, window=31, polyorder=3, closed=False)

    residual_var_xy = np.var(smoothed_xy - truth)
    residual_var_z = np.var(smoothed_z - truth)
    assert residual_var_z < residual_var_xy


@pytest.mark.slow
def test_no_self_intersection_across_ingested_circuits():
    # E-17: the invariant asserted across every ingested circuit. Skips cleanly until the
    # FastF1 cache and the built ribbons exist.
    cache_dir = REPO_ROOT / "data" / "cache" / "fastf1"
    if not cache_dir.is_dir():
        pytest.skip("no FastF1 cache — the E-17 sweep needs ingested circuits")

    built_dir = REPO_ROOT / "data" / "circuits"
    ribbons = sorted(built_dir.glob("*/ribbon.glb")) if built_dir.is_dir() else []
    if not ribbons:
        pytest.skip("no built ribbons under data/circuits — run make circuits first")

    import pygltflib

    for glb_path in ribbons:
        gltf = pygltflib.GLTF2().load(str(glb_path))
        positions = _glb_positions(gltf)
        vertices = positions.reshape(-1, 2, 3)
        assert ribbon_self_intersects(vertices) is False, f"{glb_path.parent.name}: self-intersects"


def _glb_positions(gltf):
    blob = gltf.binary_blob()
    accessor = gltf.accessors[gltf.meshes[0].primitives[0].attributes.POSITION]
    view = gltf.bufferViews[accessor.bufferView]
    start = (view.byteOffset or 0) + (accessor.byteOffset or 0)
    raw = blob[start : start + accessor.count * 3 * 4]
    return np.frombuffer(raw, dtype=np.float32).reshape(accessor.count, 3).copy()
