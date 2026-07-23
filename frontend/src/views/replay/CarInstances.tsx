// All cars in two instanced draws plus one for sprite text (5.10.3): a body mesh
// every car always gets, a detail mesh (airbox fin) that drops beyond the LOD
// distance, and a single quad InstancedMesh whose per-instance UV offset picks the
// car's code out of one atlas texture. Colours are written before first render —
// three 0.169 will not retrofit instanceColor onto a compiled program quietly.

import { useEffect, useLayoutEffect, useMemo, type MutableRefObject } from "react";
import {
  CanvasTexture,
  Color,
  DoubleSide,
  InstancedBufferAttribute,
  InstancedMesh,
  ShaderMaterial,
  SRGBColorSpace,
} from "three";

import { CAR_DIMENSIONS_M, SPRITE_LABEL_SIZE_M } from "../../config/constants";
import { carLivery } from "../../config/liveries";
import { atlasLayout, buildAtlasCanvas } from "../../lib/labelAtlas";

export interface CarMeshRefs {
  body: MutableRefObject<InstancedMesh | null>;
  detail: MutableRefObject<InstancedMesh | null>;
  sprites: MutableRefObject<InstancedMesh | null>;
}

const SPRITE_VERTEX = /* glsl */ `
  attribute vec2 aUvOffset;
  uniform vec2 uCellSize;
  varying vec2 vUv;
  void main() {
    // flipY is off, so texel v grows down the canvas while the quad's uv.y grows
    // up — mirror v or every code renders upside down
    vUv = aUvOffset + vec2(uv.x, 1.0 - uv.y) * uCellSize;
    gl_Position = projectionMatrix * modelViewMatrix * instanceMatrix * vec4(position, 1.0);
  }
`;

// operational — alpha-discard threshold: kills the glyph antialiasing fringe that
// would otherwise z-fight between overlapping labels
const SPRITE_ALPHA_CUTOFF = 0.15;

const SPRITE_FRAGMENT = /* glsl */ `
  uniform sampler2D uAtlas;
  uniform float uAlphaCutoff;
  varying vec2 vUv;
  void main() {
    vec4 texel = texture2D(uAtlas, vUv);
    if (texel.a < uAlphaCutoff) discard;
    gl_FragColor = texel;
  }
`;

interface CarInstancesProps {
  count: number;
  refs: CarMeshRefs;
  onSelect?: (carId: number) => void;
}

export default function CarInstances({ count, refs, onSelect }: CarInstancesProps) {
  const spriteMaterial = useMemo(() => {
    const codes = Array.from({ length: count }, (_, id) => carLivery(id).code);
    const colours = Array.from({ length: count }, (_, id) => carLivery(id).colour);
    const layout = atlasLayout(codes);
    const texture = new CanvasTexture(buildAtlasCanvas(codes, colours));
    texture.colorSpace = SRGBColorSpace; // without this the codes render washed out
    texture.flipY = false;
    return {
      layout,
      material: new ShaderMaterial({
        vertexShader: SPRITE_VERTEX,
        fragmentShader: SPRITE_FRAGMENT,
        uniforms: {
          uAtlas: { value: texture },
          uCellSize: { value: [layout.cellU, layout.cellV] },
          uAlphaCutoff: { value: SPRITE_ALPHA_CUTOFF },
        },
        transparent: true,
        depthWrite: false,
        side: DoubleSide,
      }),
    };
  }, [count]);

  // args-passed materials sit outside R3F's auto-dispose: free the program and
  // the atlas texture when the replay unmounts or the grid size changes
  useEffect(
    () => () => {
      (spriteMaterial.material.uniforms.uAtlas.value as CanvasTexture).dispose();
      spriteMaterial.material.dispose();
    },
    [spriteMaterial],
  );

  useLayoutEffect(() => {
    const body = refs.body.current;
    const detail = refs.detail.current;
    if (body === null || detail === null) return;
    const colour = new Color();
    for (let id = 0; id < count; id++) {
      colour.set(carLivery(id).colour);
      body.setColorAt(id, colour);
      detail.setColorAt(id, colour);
    }
    if (body.instanceColor !== null) body.instanceColor.needsUpdate = true;
    if (detail.instanceColor !== null) detail.instanceColor.needsUpdate = true;
  }, [count, refs.body, refs.detail]);

  useLayoutEffect(() => {
    const sprites = refs.sprites.current;
    if (sprites === null) return;
    const offsets = new Float32Array(count * 2);
    for (let id = 0; id < count; id++) {
      const [u, v] = spriteMaterial.layout.uvOffset(id);
      offsets[id * 2] = u;
      offsets[id * 2 + 1] = v;
    }
    sprites.geometry.setAttribute("aUvOffset", new InstancedBufferAttribute(offsets, 2));
  }, [count, refs.sprites, spriteMaterial]);

  const { length, width, height } = CAR_DIMENSIONS_M;
  return (
    <group>
      {/* frustumCulled off everywhere: the base geometry's bounding sphere knows
          nothing about instances spread around a 5 km ribbon */}
      <instancedMesh
        ref={refs.body}
        args={[undefined, undefined, count]}
        frustumCulled={false}
        onClick={(event) => {
          event.stopPropagation();
          if (event.instanceId !== undefined) onSelect?.(event.instanceId);
        }}
      >
        <boxGeometry args={[width, length, height]} />
        <meshStandardMaterial />
      </instancedMesh>
      <instancedMesh ref={refs.detail} args={[undefined, undefined, count]} frustumCulled={false}>
        {/* stylised — the LOD detail fin: a narrow airbox spine over the body,
            proportions relative to CAR_DIMENSIONS_M, visual only */}
        <boxGeometry args={[width * 0.3, length * 0.4, height * 0.8]} />
        <meshStandardMaterial />
      </instancedMesh>
      <instancedMesh
        ref={refs.sprites}
        args={[undefined, spriteMaterial.material, count]}
        frustumCulled={false}
      >
        <planeGeometry args={[SPRITE_LABEL_SIZE_M, SPRITE_LABEL_SIZE_M / 2]} />
      </instancedMesh>
    </group>
  );
}
