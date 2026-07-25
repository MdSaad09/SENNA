// The one definition of the stylised scene rig: a flat two-light setup and the Z-up
// rotation (the F04 GLB keeps elevation on its third component). CanvasHost wraps
// its whole scene in this; the counterfactual panes each mount their own, because
// drei View children portal into private scenes that never see the root's lights.

import type { ReactNode } from "react";

export default function SceneFrame({ children }: { children?: ReactNode }) {
  return (
    <>
      {/* stylised — enough ambient to keep shadowed ribbon readable, one keylight
          for car-body shading; nothing physical */}
      <ambientLight intensity={0.7} />
      <directionalLight position={[600, 900, 400]} intensity={1.1} />
      <group rotation={[-Math.PI / 2, 0, 0]}>{children}</group>
    </>
  );
}
