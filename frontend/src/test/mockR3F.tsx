// vi.mock factories for the R3F boundary — jsdom has no WebGL, so Canvas becomes a
// bare <canvas> that swallows its children and drei's Html becomes a plain div.
// vi.mock hoists its callback above every import, so test files must load this
// module dynamically inside the callback rather than capture anything top-level:
//   vi.mock("@react-three/fiber", async () => (await import("./test/mockR3F")).fiberMock());
import type { ReactNode } from "react";

import { gltfStub } from "./ribbonFixture";

export function fiberMock() {
  return {
    Canvas: (_props: { children?: ReactNode }) => <canvas data-testid="r3f-canvas" />,
    useFrame: () => undefined,
    useThree: () => ({}),
  };
}

export function dreiMock() {
  const useGLTF = Object.assign(() => gltfStub, { preload: () => undefined });
  return {
    Html: ({ children }: { children?: ReactNode }) => (
      <div data-testid="html-label">{children}</div>
    ),
    Text: () => null,
    OrbitControls: () => null,
    useGLTF,
  };
}
