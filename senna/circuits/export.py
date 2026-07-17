"""GLTF export: turn the ribbon edges into a triangle mesh the frontend loads.

The strip is two triangles per quad between consecutive stations, with the left
and right edge vertices interleaved per station so the buffer reshapes straight
back to (N, 2, 3). Binary GLB keeps geometry and buffer in one file per circuit
(5.10.1 item 7); the sidecar JSON carries lap length and the stylised flags.
"""

import json
from pathlib import Path

import numpy as np
import pygltflib


def ribbon_mesh(vertices: np.ndarray, *, closed: bool = False) -> tuple[np.ndarray, np.ndarray]:
    """(N, 2, 3) ribbon edges to (positions (2N, 3) float32, triangles uint32).

    A closed circuit adds the wrap quad from the last station back to the first,
    so the ring seals with no duplicated seam vertex — 2N triangles closed, or
    2(N-1) for an open strip.
    """
    station_count = vertices.shape[0]
    positions = vertices.reshape(2 * station_count, 3).astype(np.float32)

    quad_count = station_count if closed else station_count - 1
    triangles = np.empty((2 * quad_count, 3), dtype=np.uint32)
    for quad in range(quad_count):
        here, ahead = quad, (quad + 1) % station_count
        left, right = 2 * here, 2 * here + 1
        next_left, next_right = 2 * ahead, 2 * ahead + 1
        triangles[2 * quad] = (left, right, next_left)
        triangles[2 * quad + 1] = (right, next_right, next_left)
    return positions, triangles


def write_glb(path: str | Path, vertices: np.ndarray, *, closed: bool = False) -> None:
    positions, triangles = ribbon_mesh(vertices, closed=closed)
    indices = triangles.reshape(-1)

    position_bytes = positions.tobytes()
    index_bytes = indices.tobytes()
    blob = position_bytes + index_bytes

    gltf = pygltflib.GLTF2(
        scene=0,
        scenes=[pygltflib.Scene(nodes=[0])],
        nodes=[pygltflib.Node(mesh=0)],
        meshes=[
            pygltflib.Mesh(
                primitives=[
                    pygltflib.Primitive(attributes=pygltflib.Attributes(POSITION=0), indices=1)
                ]
            )
        ],
        accessors=[
            pygltflib.Accessor(
                bufferView=0,
                componentType=pygltflib.FLOAT,
                count=len(positions),
                type=pygltflib.VEC3,
                min=positions.min(axis=0).tolist(),
                max=positions.max(axis=0).tolist(),
            ),
            pygltflib.Accessor(
                bufferView=1,
                componentType=pygltflib.UNSIGNED_INT,
                count=len(indices),
                type=pygltflib.SCALAR,
            ),
        ],
        bufferViews=[
            pygltflib.BufferView(
                buffer=0,
                byteOffset=0,
                byteLength=len(position_bytes),
                target=pygltflib.ARRAY_BUFFER,
            ),
            pygltflib.BufferView(
                buffer=0,
                byteOffset=len(position_bytes),
                byteLength=len(index_bytes),
                target=pygltflib.ELEMENT_ARRAY_BUFFER,
            ),
        ],
        buffers=[pygltflib.Buffer(byteLength=len(blob))],
    )
    gltf.set_binary_blob(blob)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    gltf.save(str(path))


def write_metadata(path: str | Path, meta: dict) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(meta, indent=2, ensure_ascii=False))
