import { expect, test } from "vitest";

import { bloomDefault } from "./gpuHeuristic";

// Table of unmasked renderer strings against the conservative default: bloom only
// switches on for silicon known to hold 60 fps with a compose pass; anything
// unrecognised, software or mobile stays off.
const VERDICTS: [string | null, boolean][] = [
  [null, false],
  ["", false],
  ["Google SwiftShader", false],
  ["ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device))", false],
  ["llvmpipe (LLVM 15.0.7, 256 bits)", false],
  ["Software Rasterizer", false],
  ["Mali-G78", false],
  ["Adreno (TM) 740", false],
  ["PowerVR Rogue GE8320", false],
  ["ANGLE (Intel, Intel(R) UHD Graphics 620, OpenGL 4.1)", false],
  ["Wizzo 9000", false], // unknown silicon: off, never a guess
  ["NVIDIA GeForce RTX 3060", true],
  ["nvidia geforce rtx 4070", true],
  ["ANGLE (NVIDIA, NVIDIA GeForce GTX 1660/PCIe/SSE2)", true], // the reference GPU
  ["AMD Radeon RX 6800 XT", true],
  ["ANGLE (Apple, Apple M2 Max, OpenGL 4.1)", true],
];

test("bloom defaults follow the renderer-string table", () => {
  for (const [renderer, wanted] of VERDICTS) {
    expect(bloomDefault(renderer), `renderer: ${JSON.stringify(renderer)}`).toBe(wanted);
  }
});

test("a driver that hides the renderer entirely keeps bloom off", () => {
  // WEBGL_debug_renderer_info is optional; some browsers return nothing at all
  expect(bloomDefault(undefined as unknown as string | null)).toBe(false);
});
