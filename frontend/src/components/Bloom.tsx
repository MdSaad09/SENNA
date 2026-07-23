// The only postprocessing in the budget (5.10.3): bloom via three's own composer,
// mounted solely while the quality toggle is on. A positive useFrame priority makes
// R3F hand the render to the composer; unmounting disposes the composer AND the
// bloom pass — EffectComposer.dispose() in three 0.169 skips its passes' own render
// targets, and UnrealBloomPass holds five mip pairs.

import { useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo } from "react";
import { Vector2 } from "three";
import { EffectComposer } from "three/examples/jsm/postprocessing/EffectComposer.js";
import { RenderPass } from "three/examples/jsm/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/examples/jsm/postprocessing/UnrealBloomPass.js";

import { BLOOM_RADIUS, BLOOM_STRENGTH, BLOOM_THRESHOLD } from "../config/constants";

export default function Bloom() {
  const { gl, scene, camera, size } = useThree();

  const { composer, bloomPass } = useMemo(() => {
    const built = new EffectComposer(gl);
    built.addPass(new RenderPass(scene, camera));
    const pass = new UnrealBloomPass(
      new Vector2(size.width, size.height),
      BLOOM_STRENGTH,
      BLOOM_RADIUS,
      BLOOM_THRESHOLD,
    );
    built.addPass(pass);
    return { composer: built, bloomPass: pass };
    // size changes go through setSize below rather than a rebuild
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gl, scene, camera]);

  useEffect(() => {
    composer.setSize(size.width, size.height);
  }, [composer, size]);

  useEffect(
    () => () => {
      bloomPass.dispose();
      composer.dispose();
    },
    [composer, bloomPass],
  );

  useFrame(() => composer.render(), 1);
  return null;
}
