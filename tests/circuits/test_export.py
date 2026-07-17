import json

import numpy as np

from senna.circuits.export import ribbon_mesh, write_glb, write_metadata
from senna.circuits.geometry import lap_length_m, within_tolerance


def straight_ribbon(n, half_width_m=6.0):
    x = np.linspace(0.0, 100.0, n)
    centreline = np.column_stack([x, np.zeros(n), np.zeros(n)])
    left = centreline + np.array([0.0, half_width_m, 0.0])
    right = centreline - np.array([0.0, half_width_m, 0.0])
    return np.stack([left, right], axis=1)


def test_glb_roundtrips_with_ribbon_mesh(tmp_path):
    import pygltflib

    n = 12
    vertices = straight_ribbon(n)
    positions, indices = ribbon_mesh(vertices)

    assert positions.shape == (2 * n, 3)
    assert positions.dtype == np.float32
    assert indices.shape == (2 * (n - 1), 3)
    assert indices.dtype == np.uint32
    # left/right interleaved per station so the strip can be reconstructed by reshape
    np.testing.assert_allclose(positions, vertices.reshape(2 * n, 3).astype(np.float32))

    out = tmp_path / "ribbon.glb"
    write_glb(out, vertices)

    gltf = pygltflib.GLTF2().load(str(out))
    counts = {accessor.count for accessor in gltf.accessors}
    assert 2 * n in counts  # position accessor: 2N vec3 vertices
    assert 3 * 2 * (n - 1) in counts  # index accessor: 3T scalar indices


def test_metadata_json_carries_stylised_flags(tmp_path):
    meta = {
        "slug": "monaco_grand_prix",
        "lap_length_m": 3337.0,
        "flags": {"elevation": "stylised", "banking": "stylised", "xmode": "stylised"},
    }
    out = tmp_path / "meta.json"

    write_metadata(out, meta)

    reloaded = json.loads(out.read_text())
    assert reloaded["flags"]["elevation"] == "stylised"
    assert reloaded["flags"]["banking"] == "stylised"
    assert reloaded["flags"]["xmode"] == "stylised"


def test_lap_length_within_5pct():
    radius_m = 800.0
    theta = np.linspace(0.0, 2 * np.pi, 2000)
    centreline = np.column_stack(
        [radius_m * np.cos(theta), radius_m * np.sin(theta), np.zeros_like(theta)]
    )
    official_m = 2 * np.pi * radius_m

    measured_m = lap_length_m(centreline, closed=True)

    assert within_tolerance(measured_m, official_m, tolerance_pct=5.0) is True
    assert within_tolerance(official_m * 1.10, official_m, tolerance_pct=5.0) is False
