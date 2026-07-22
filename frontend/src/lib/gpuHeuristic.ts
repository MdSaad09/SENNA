// Bloom's default follows the unmasked renderer string: on only for silicon known
// to hold 60 fps with a compose pass, off for software rasterisers, mobile GPUs,
// integrated graphics and anything unrecognised. The quality toggle always
// overrides; this only picks the starting position (5.10.3).

const NEVER = ["swiftshader", "llvmpipe", "software", "mali", "adreno", "powervr", "intel"];
const KNOWN_FAST = ["geforce", "rtx", "radeon rx", "apple m"];

export function bloomDefault(renderer: string | null): boolean {
  if (!renderer) return false;
  const lowered = renderer.toLowerCase();
  if (NEVER.some((mark) => lowered.includes(mark))) return false;
  return KNOWN_FAST.some((mark) => lowered.includes(mark));
}
